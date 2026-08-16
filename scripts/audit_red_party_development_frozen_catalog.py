#!/usr/bin/env python3
"""Independently reconstruct Red's frozen 8+6 inputs without opening answers."""

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
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.gen1_cartridge import evolution_graph  # noqa: E402
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import PartyMemberObservation  # noqa: E402
from pokemon_red_completion.party_development_adapter import (  # noqa: E402
    BoundPartyDevelopmentMenu,
)
from pokemon_red_completion.party_development_frozen_catalog import (  # noqa: E402
    PartyDevelopmentFrozenCatalog,
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_rank import (  # noqa: E402
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    EvolutionRouteKind,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
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
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RedPartyDevelopmentQuestionPreflight,
    build_red_party_development_snapshot,
)
from pokemon_red_completion.red_party_development_pp_materialization import (  # noqa: E402
    RedPartyDevelopmentPpMaterializationPlan,
    RedPpMaterializationSource,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.team_training import GrindingArea  # noqa: E402
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingChoiceKind,
)

_MAX_JSON_BYTES = 8 * 1024 * 1024
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_CI_RUN_JSON_FIELDS = "attempt,conclusion,databaseId,event,headSha,status,url,workflowName"
_ABSOLUTE_PATH = re.compile(r"(?i)(?:\A/|\A~[/\\]|\A[a-z]:[/\\]|\A\\\\|\Afile:)")
_FORBIDDEN_TARGET_KEYS = {
    "learner_outcome",
    "outcome_target",
    "selected_candidate_index",
    "teacher_choice_target",
}


class RedPartyDevelopmentFrozenCatalogAuditError(RuntimeError):
    """Raised when one frozen input cannot be independently reconstructed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--catalog-file-sha256", required=True)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--previous-inventory", type=Path, required=True)
    parser.add_argument("--previous-inventory-file-sha256", required=True)
    parser.add_argument("--current-inventory", type=Path, required=True)
    parser.add_argument("--current-inventory-file-sha256", required=True)
    parser.add_argument("--pp-plan", type=Path, required=True)
    parser.add_argument("--pp-plan-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--train-artifact-manifest-sha256", required=True)
    parser.add_argument("--development-artifact-manifest-sha256", required=True)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_private_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> tuple[Mapping[str, object], bytes]:
    resolved = _require_external(path, subject=subject)
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            f"private {subject} must be a regular file"
        )
    payload = resolved.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            f"private {subject} file digest or size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            f"private {subject} is not valid ASCII JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentFrozenCatalogAuditError(f"private {subject} is not an object")
    return value, payload


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
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen-catalog audit CI binding is invalid"
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
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen-catalog audit could not authenticate exact CI"
        ) from error
    if completed.returncode != 0:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen-catalog audit could not authenticate exact CI"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen-catalog audit CI evidence is invalid"
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
        or type(document.get("attempt")) is not int  # noqa: E721
        or document.get("attempt") != exact_ci_attempt
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen-catalog audit CI is not the exact successful source-bound run"
        )
    return document


def _require_no_path_or_target(value: object) -> None:
    if isinstance(value, Mapping):
        if any(key in _FORBIDDEN_TARGET_KEYS for key in value):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "frozen catalog contains a prohibited target field"
            )
        for key, item in value.items():
            if not isinstance(key, str):
                raise RedPartyDevelopmentFrozenCatalogAuditError(
                    "frozen catalog contains a non-text key"
                )
            _require_no_path_or_target(item)
    elif isinstance(value, list):
        for item in value:
            _require_no_path_or_target(item)
    elif isinstance(value, str) and _ABSOLUTE_PATH.search(value) is not None:
        raise RedPartyDevelopmentFrozenCatalogAuditError("frozen catalog contains a private path")


def _require_inventory_extension(
    previous: PartyDevelopmentCheckpointInventory,
    current: PartyDevelopmentCheckpointInventory,
    *,
    output_capture_ids: set[str],
) -> None:
    previous_by_id = {item.checkpoint_id: item for item in previous.entries}
    current_by_id = {item.checkpoint_id: item for item in current.entries}
    if (
        len(output_capture_ids) != 2
        or len(current.entries) != len(previous.entries) + 2
        or set(current_by_id) - set(previous_by_id) != output_capture_ids
        or any(current_by_id[key] != value for key, value in previous_by_id.items())
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "catalog inventory is not the exact historical inventory plus two states"
        )


def _entry_matches_reservation_source(
    entry: PartyDevelopmentInventoryEntry,
    reservation: PartyDevelopmentQuestionReservation,
) -> bool:
    hp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.hp_bin for member in entry.members}
    )
    pp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.pp_bin for member in entry.members}
    )
    routes = tuple(
        route
        for route in EvolutionRouteKind
        if route in {item for member in entry.members for item in member.evolution_routes}
    )
    return (
        entry.checkpoint_id == reservation.source_checkpoint_id
        and entry.partition is reservation.partition
        and entry.controls_ready
        and not entry.battle_active
        and entry.state_sha256 == reservation.source_state_sha256
        and entry.envelope_sha256 == reservation.source_envelope_sha256
        and entry.semantic_signature_sha256 == reservation.source_semantic_signature_sha256
        and len(entry.members) == reservation.source_member_count
        and sum(member.trainable for member in entry.members) == reservation.source_trainable_count
        and hp_bins == reservation.source_hp_bins
        and pp_bins == reservation.source_pp_bins
        and routes == reservation.source_evolution_route_kinds
        and reservation.goal in entry.goal_hints
    )


def _post_materialization_reservation(
    reservation: PartyDevelopmentQuestionReservation,
    entry: PartyDevelopmentInventoryEntry,
) -> PartyDevelopmentQuestionReservation:
    if (
        entry.partition is not reservation.partition
        or not entry.controls_ready
        or entry.battle_active
        or reservation.goal not in entry.goal_hints
        or sum(member.trainable for member in entry.members) < 2
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "prepared question is not a ready goal-relevant context"
        )
    hp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.hp_bin for member in entry.members}
    )
    pp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.pp_bin for member in entry.members}
    )
    routes = tuple(
        route
        for route in EvolutionRouteKind
        if route in {item for member in entry.members for item in member.evolution_routes}
    )
    return replace(
        reservation,
        source_checkpoint_id=entry.checkpoint_id,
        source_state_sha256=entry.state_sha256,
        source_envelope_sha256=entry.envelope_sha256,
        source_semantic_signature_sha256=entry.semantic_signature_sha256,
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
    *,
    capture_id: str,
    profile_id: str,
) -> tuple[Path, Path, Path]:
    state = catalog_root / "captures" / f"{capture_id}.state"
    envelope = state.with_suffix(".state.json")
    profile = catalog_root / "profiles" / f"{profile_id}.json"
    for directory in (state.parent, profile.parent):
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "catalog question directory is invalid"
            )
    for path in (state, envelope, profile):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "catalog question input is not a regular file"
            )
    return state, envelope, profile


def _manifest_sha256(private_root: Path, artifact_id: str) -> str:
    directory = private_root / artifact_id
    manifest = directory / "manifest.json"
    directory_metadata = directory.lstat()
    manifest_metadata = manifest.lstat()
    if (
        not stat.S_ISDIR(directory_metadata.st_mode)
        or stat.S_ISLNK(directory_metadata.st_mode)
        or not stat.S_ISREG(manifest_metadata.st_mode)
        or stat.S_ISLNK(manifest_metadata.st_mode)
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError("materialization manifest path is invalid")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _run(args: argparse.Namespace) -> dict[str, object]:
    audit_script_path = Path(__file__).resolve()
    audit_script_sha256 = hashlib.sha256(audit_script_path.read_bytes()).hexdigest()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guard owns this
        raise AssertionError("published catalog audit lost its source commit")
    ci = _require_exact_green_ci_run(
        args.exact_ci_run,
        args.exact_ci_attempt,
        source_commit=source.git_commit,
    )
    paths = {
        "catalog": _require_external(args.catalog, subject="frozen catalog"),
        "reservation": _require_external(args.reservation_plan, subject="reservation plan"),
        "previous_inventory": _require_external(
            args.previous_inventory, subject="previous inventory"
        ),
        "current_inventory": _require_external(args.current_inventory, subject="current inventory"),
        "pp_plan": _require_external(args.pp_plan, subject="PP plan"),
        "venue_registry": _require_external(args.venue_prior_registry, subject="venue registry"),
        "catalog_root": _require_external(args.catalog_root, subject="catalog root"),
        "context_catalog": _require_external(args.context_catalog, subject="context catalog"),
        "private_root": _require_external(args.private_artifact_root, subject="artifact root"),
    }
    if len(set(paths.values())) != len(paths):
        raise RedPartyDevelopmentFrozenCatalogAuditError("catalog audit paths collide")
    catalog_document, catalog_payload = _load_private_json(
        paths["catalog"],
        expected_sha256=args.catalog_file_sha256,
        subject="frozen catalog",
    )
    _require_no_path_or_target(catalog_document)
    catalog = PartyDevelopmentFrozenCatalog.from_private_dict(catalog_document)
    reservation_document, _ = _load_private_json(
        paths["reservation"],
        expected_sha256=args.reservation_plan_file_sha256,
        subject="reservation plan",
    )
    previous_document, _ = _load_private_json(
        paths["previous_inventory"],
        expected_sha256=args.previous_inventory_file_sha256,
        subject="previous inventory",
    )
    current_document, _ = _load_private_json(
        paths["current_inventory"],
        expected_sha256=args.current_inventory_file_sha256,
        subject="current inventory",
    )
    pp_document, _ = _load_private_json(
        paths["pp_plan"],
        expected_sha256=args.pp_plan_file_sha256,
        subject="PP plan",
    )
    venue_document, _ = _load_private_json(
        paths["venue_registry"],
        expected_sha256=args.venue_prior_registry_file_sha256,
        subject="venue registry",
    )
    context_document, context_payload = _load_private_json(
        paths["context_catalog"],
        expected_sha256=args.context_catalog_file_sha256,
        subject="context catalog",
    )
    reservation_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        reservation_document
    )
    previous_inventory = PartyDevelopmentCheckpointInventory.from_private_dict(previous_document)
    current_inventory = PartyDevelopmentCheckpointInventory.from_private_dict(current_document)
    pp_plan = RedPartyDevelopmentPpMaterializationPlan.from_private_dict(pp_document)
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(venue_document)
    if (
        catalog.reservation_plan_file_sha256 != args.reservation_plan_file_sha256
        or catalog.reservation_plan_sha256 != reservation_plan.plan_sha256
        or catalog.inventory_file_sha256 != args.current_inventory_file_sha256
        or catalog.inventory_sha256 != current_inventory.inventory_sha256
        or catalog.pp_plan_file_sha256 != args.pp_plan_file_sha256
        or catalog.pp_plan_sha256 != pp_plan.plan_sha256
        or catalog.context_catalog_file_sha256 != args.context_catalog_file_sha256
        or catalog.venue_prior_registry_file_sha256 != args.venue_prior_registry_file_sha256
        or catalog.venue_prior_registry_sha256 != venue_registry.registry_sha256
        or pp_plan.reservation_plan_file_sha256 != args.reservation_plan_file_sha256
        or pp_plan.reservation_plan_sha256 != reservation_plan.plan_sha256
        or pp_plan.inventory_file_sha256 != args.previous_inventory_file_sha256
        or pp_plan.inventory_sha256 != previous_inventory.inventory_sha256
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen catalog crosses its authenticated input lineage"
        )
    committed_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=catalog.source_commit,
    )
    loaded_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    audit_committed_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if (
        committed_bundle != catalog.source_bundle_sha256
        or loaded_bundle != committed_bundle
        or audit_committed_bundle != loaded_bundle
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "loaded reconstruction logic differs from the frozen catalog source"
        )
    output_ids = {entry.output_capture_id for entry in pp_plan.entries}
    _require_inventory_extension(
        previous_inventory,
        current_inventory,
        output_capture_ids=output_ids,
    )
    previous_by_id = {item.checkpoint_id: item for item in previous_inventory.entries}
    current_by_id = {item.checkpoint_id: item for item in current_inventory.entries}
    reservation_by_scenario = {item.scenario_id: item for item in reservation_plan.reservations}
    question_by_scenario = {item.scenario_id: item for item in catalog.questions}
    pp_by_scenario = {item.scenario_id: item for item in pp_plan.entries}
    prepared_scenarios = {
        item.scenario_id
        for item in reservation_plan.reservations
        if item.preparation is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    }
    if (
        set(question_by_scenario) != set(reservation_by_scenario)
        or set(pp_by_scenario) != prepared_scenarios
        or len(pp_plan.entries) != 2
        or Counter(item.partition for item in pp_plan.entries)
        != {
            ScenarioPartition.TRAIN: 1,
            ScenarioPartition.DEVELOPMENT: 1,
        }
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "catalog scenarios do not exactly match the reserved 8+6 layout"
        )
    catalog_root = paths["catalog_root"]
    private_root = paths["private_root"]
    open_private_root(private_root, repository_root=PROJECT_ROOT)
    expected_manifest = {
        ScenarioPartition.TRAIN: args.train_artifact_manifest_sha256,
        ScenarioPartition.DEVELOPMENT: (args.development_artifact_manifest_sha256),
    }
    observed_artifact_ids: set[str] = set()
    observed_manifest_sha256: set[str] = set()
    materialization_manifest_paths: list[Path] = []
    for entry in pp_plan.entries:
        artifact_id = f"red-party-pp-materialization-v1-{entry.partition.value}"
        manifest_sha256 = _manifest_sha256(private_root, artifact_id)
        if manifest_sha256 != expected_manifest[entry.partition]:
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "materialization manifest differs from the frozen question"
            )
        observed_artifact_ids.add(artifact_id)
        observed_manifest_sha256.add(manifest_sha256)
        materialization_manifest_paths.append(private_root / artifact_id / "manifest.json")
    if len(observed_artifact_ids) != 2 or len(observed_manifest_sha256) != 2:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "materialization identities are not independent by partition"
        )
    context_source_commit = context_document.get("source_commit")
    if not isinstance(context_source_commit, str):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "historical context catalog source is invalid"
        )
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        context_payload,
        historical_registry,
    )
    if (
        context_catalog.catalog_sha256 != catalog.context_catalog_sha256
        or context_catalog.catalog_sha256 != pp_plan.context_catalog_sha256
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "historical context catalog semantics differ"
        )
    route_area = ROUTE_11_TRAINING_VENUE.band
    cave_area = DIGLETTS_CAVE_TRAINING_VENUE.band
    route_evidence = venue_registry.evidence_for(route_area)
    cave_evidence = venue_registry.evidence_for(cave_area)
    if route_evidence is None or cave_evidence is None:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "catalog audit lacks both frozen venue priors"
        )
    areas = (route_area, cave_area)
    contracts = (
        route_evidence.operational_contract_sha256,
        cave_evidence.operational_contract_sha256,
    )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != catalog.rom_sha256 or fingerprint.sha256 != pp_plan.rom_sha256:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "catalog audit ROM differs from the frozen inputs"
        )
    evolutions = evolution_graph(rom_path.read_bytes())
    protected_expected = {
        paths["catalog"]: args.catalog_file_sha256,
        paths["reservation"]: args.reservation_plan_file_sha256,
        paths["previous_inventory"]: args.previous_inventory_file_sha256,
        paths["current_inventory"]: args.current_inventory_file_sha256,
        paths["pp_plan"]: args.pp_plan_file_sha256,
        paths["venue_registry"]: args.venue_prior_registry_file_sha256,
        paths["context_catalog"]: args.context_catalog_file_sha256,
        rom_path: catalog.rom_sha256,
    }
    for entry, manifest_path in zip(
        pp_plan.entries,
        materialization_manifest_paths,
        strict=True,
    ):
        protected_expected[manifest_path] = expected_manifest[entry.partition]
    protected_before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected_expected
    }
    if protected_before != protected_expected:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "protected catalog input differs from its authorized digest"
        )
    adjacent_before = rom_adjacent_artifacts(rom_path)
    candidate_menu_sha256: list[str] = []
    total_candidate_rows = 0
    all_feature_rows: list[tuple[float, ...]] = []
    prepared_partition_counts: Counter[str] = Counter()
    for scenario_id in sorted(question_by_scenario):
        question = question_by_scenario[scenario_id]
        original = reservation_by_scenario[scenario_id]
        pp_entry: RedPpMaterializationSource | None = pp_by_scenario.get(scenario_id)
        original_inventory_entry = previous_by_id.get(original.source_checkpoint_id)
        if (
            original_inventory_entry is None
            or not _entry_matches_reservation_source(
                original_inventory_entry,
                original,
            )
            or question.binding.partition is not original.partition
            or question.binding.kind is not original.kind
            or question.binding.goal is not original.goal
            or question.binding.root_lineage_id in set(reservation_plan.excluded_root_lineage_ids)
        ):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "frozen question semantics or root exclusion differs from its reservation"
            )
        if pp_entry is None:
            if (
                original.preparation is not PartyDevelopmentContextPreparation.NONE
                or question.capture_id != original.source_checkpoint_id
                or question.profile_id != original.source_checkpoint_id
                or question.capture_envelope_sha256 != original.source_envelope_sha256
                or question.binding.initial_state_sha256 != original.source_state_sha256
                or question.materialization_artifact_id is not None
                or question.materialization_manifest_sha256 is not None
            ):
                raise RedPartyDevelopmentFrozenCatalogAuditError(
                    "direct frozen question differs from its reserved source"
                )
            reservation = original
        else:
            artifact_id = f"red-party-pp-materialization-v1-{pp_entry.partition.value}"
            output = current_by_id.get(pp_entry.output_capture_id)
            source_entry = previous_by_id.get(pp_entry.source_checkpoint_id)
            if (
                original.preparation is not PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
                or source_entry is None
                or output is None
                or pp_entry.source_checkpoint_id != original.source_checkpoint_id
                or pp_entry.source_state_sha256 != original.source_state_sha256
                or source_entry.state_sha256 != original.source_state_sha256
                or source_entry.envelope_sha256 != original.source_envelope_sha256
                or question.capture_id != pp_entry.output_capture_id
                or question.profile_id != original.source_checkpoint_id
                or question.capture_envelope_sha256 != output.envelope_sha256
                or question.binding.initial_state_sha256 != output.state_sha256
                or question.binding.root_lineage_id != pp_entry.source_root_lineage_id
                or question.materialization_artifact_id != artifact_id
                or question.materialization_manifest_sha256 != expected_manifest[pp_entry.partition]
                or "middle" not in {member.pp_bin for member in output.members}
                or output.state_sha256 in set(reservation_plan.excluded_state_sha256)
            ):
                raise RedPartyDevelopmentFrozenCatalogAuditError(
                    "prepared frozen question differs from its source and output lineage"
                )
            reservation = _post_materialization_reservation(original, output)
            prepared_partition_counts[pp_entry.partition.value] += 1
        state_path, envelope_path, profile_path = _question_paths(
            catalog_root,
            capture_id=reservation.source_checkpoint_id,
            profile_id=question.profile_id,
        )
        question_files_before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path, profile_path)
        }
        if question_files_before[profile_path] != question.profile_file_sha256:
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "frozen question profile file digest differs"
            )
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        loaded = load_captured_progress(envelope_path, state_path=state_path)
        if (
            capture.capture_id != reservation.source_checkpoint_id
            or capture.state_sha256 != reservation.source_state_sha256
            or capture.envelope_sha256 != reservation.source_envelope_sha256
            or loaded.checkpoint_id != capture.capture_id
            or loaded.state_sha256 != capture.state_sha256
        ):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "frozen question capture and envelope do not reconstruct"
            )
        profile = load_red_goal_context_profile(profile_path)
        original_entry = context_catalog.entry(question.profile_id)
        root_lineage_id = original_entry.authenticated_root_lineage_id(
            slot_id=question.profile_id,
            capture_id=question.profile_id,
            state_sha256=original.source_state_sha256,
            envelope_sha256=original.source_envelope_sha256,
        )
        if root_lineage_id != question.binding.root_lineage_id or root_lineage_id in set(
            reservation_plan.excluded_root_lineage_ids
        ):
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "frozen question loses its authenticated root lineage"
            )
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
        snapshot = build_red_party_development_snapshot(
            reservation,
            source_root_lineage_id=root_lineage_id,
            observation=observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
            areas=areas,
            venue_prior_registry=venue_registry,
            venue_operational_contract_sha256=contracts,
            source_commit=catalog.source_commit,
            source_bundle_sha256=catalog.source_bundle_sha256,
        )
        menu: (
            BoundPartyDevelopmentMenu[PartyMemberObservation]
            | BoundPartyDevelopmentMenu[GrindingArea]
            | None
        )
        if original.kind is TrainingChoiceKind.TRAINEE:
            menu = snapshot.trainee_menu(route_area)
        else:
            menu = snapshot.venue_menu(snapshot.unique_weakest_goal_relevant_venue_trainee())
        if menu is None or sum(menu.candidate_available) < 2:
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "reconstructed frozen question lacks two available candidates"
            )
        binding = snapshot.freeze_binding(menu, scenario_id=scenario_id)
        RedPartyDevelopmentQuestionPreflight(
            reservation=reservation,
            source_root_lineage_id=root_lineage_id,
            snapshot=snapshot,
            menu=menu,
            binding=binding,
        )
        expected_question = PartyDevelopmentFrozenQuestion(
            capture_id=reservation.source_checkpoint_id,
            capture_envelope_sha256=reservation.source_envelope_sha256,
            profile_id=question.profile_id,
            profile_file_sha256=question.profile_file_sha256,
            binding=binding,
            candidate_set=menu.candidate_set,
            materialization_artifact_id=question.materialization_artifact_id,
            materialization_manifest_sha256=(question.materialization_manifest_sha256),
        )
        if expected_question != question:
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "reconstructed features or binding differ from the frozen question"
            )
        question_files_after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in question_files_before
        }
        if question_files_after != question_files_before:
            raise RedPartyDevelopmentFrozenCatalogAuditError(
                "question reconstruction changed a source file"
            )
        candidate_menu_sha256.append(canonical_sha256(question.candidate_set.public_dict()))
        total_candidate_rows += len(question.candidate_set.candidates)
        all_feature_rows.extend(item.features for item in question.candidate_set.candidates)
    if prepared_partition_counts != {"development": 1, "train": 1}:
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "frozen catalog lacks one independent preparation per partition"
        )
    if (
        {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected_expected}
        != protected_before
        or rom_adjacent_artifacts(rom_path) != adjacent_before
        or hashlib.sha256(catalog_payload).hexdigest() != args.catalog_file_sha256
        or hashlib.sha256(audit_script_path.read_bytes()).hexdigest() != audit_script_sha256
    ):
        raise RedPartyDevelopmentFrozenCatalogAuditError(
            "read-only catalog audit changed a protected input"
        )
    feature_columns = tuple(zip(*all_feature_rows, strict=True))
    partitions = Counter(item.binding.partition.value for item in catalog.questions)
    kinds = Counter(
        f"{item.binding.partition.value}:{item.binding.kind.value}" for item in catalog.questions
    )
    goals = Counter(
        f"{item.binding.partition.value}:{item.binding.goal.value}" for item in catalog.questions
    )
    widths = Counter(
        f"{item.binding.partition.value}:{len(item.candidate_set.candidates)}"
        for item in catalog.questions
    )
    return {
        "schema": "pokemon.red.party-development-frozen-catalog-audit.v1",
        "status": "approve_input_integrity_outcomes_closed",
        "audit_source_commit": source.git_commit,
        "audit_source_bundle_sha256": loaded_bundle,
        "audit_script_sha256": audit_script_sha256,
        "exact_ci_run": ci["databaseId"],
        "exact_ci_attempt": ci["attempt"],
        "exact_ci_conclusion": ci["conclusion"],
        "catalog_file_sha256": args.catalog_file_sha256,
        "catalog_sha256": catalog.catalog_sha256,
        "prospective_catalog_sha256": catalog.prospective_catalog_sha256,
        "catalog_source_commit": catalog.source_commit,
        "catalog_source_bundle_sha256": catalog.source_bundle_sha256,
        "committed_catalog_source_reproduced": True,
        "question_count": len(catalog.questions),
        "partition_counts": dict(sorted(partitions.items())),
        "choice_kind_partition_counts": dict(sorted(kinds.items())),
        "goal_partition_counts": dict(sorted(goals.items())),
        "candidate_width_partition_counts": dict(sorted(widths.items())),
        "candidate_row_count": total_candidate_rows,
        "feature_column_count": len(PARTY_DEVELOPMENT_FEATURE_NAMES),
        "nonconstant_feature_column_count": sum(len(set(column)) > 1 for column in feature_columns),
        "distinct_candidate_menu_count": len(set(candidate_menu_sha256)),
        "reservation_joins_reconstructed": len(catalog.questions),
        "capture_envelope_joins_reconstructed": len(catalog.questions),
        "source_profile_joins_reconstructed": len(catalog.questions),
        "root_lineages_reconstructed": len(catalog.questions),
        "candidate_feature_menus_reconstructed": len(catalog.questions),
        "prepared_partition_counts": dict(sorted(prepared_partition_counts.items())),
        "historical_checkpoint_count": len(previous_inventory.entries),
        "re_inventory_checkpoint_count": len(current_inventory.entries),
        "new_prepared_checkpoint_count": 2,
        "venue_prior_count": len(venue_registry.entries),
        "input_files_unchanged": True,
        "rom_adjacent_artifacts_unchanged": True,
        "candidate_feature_values_public": False,
        "capture_identity_public": False,
        "profile_identity_public": False,
        "answers_selected": 0,
        "outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error("Frozen catalog audit failed closed; private paths were withheld.")
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
