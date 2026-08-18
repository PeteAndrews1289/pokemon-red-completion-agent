#!/usr/bin/env python3
"""Build a private Red context plan that adds source-local development to unused capture roots."""

# ruff: noqa: E402 -- pin the reviewed workspace source before project imports

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import cast

_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP_SRC = _BOOTSTRAP_PROJECT_ROOT / "src"
_PRELOADED_PROJECT_MODULES = tuple(
    sorted(
        name
        for name in sys.modules
        if name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.")
    )
)
while str(_BOOTSTRAP_SRC) in sys.path:
    sys.path.remove(str(_BOOTSTRAP_SRC))
sys.path.insert(0, str(_BOOTSTRAP_SRC))

from pokemon_red_completion.collection_protocol import (
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalog,
    GoalManagerContextCatalogError,
    parse_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerCollectionRegistry,
    GoalManagerProtocolError,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    build_acquisition_replanning_profile_payload,
    parse_red_goal_context_profile,
)

PROJECT_ROOT = _BOOTSTRAP_PROJECT_ROOT
PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
REPEATABLE_SCHEMA = "pokemon.red.repeatable-goal-manager-development-campaign.v1"
PAIRED_SCHEMA = "pokemon.red.paired-goal-manager-outcome-screen.v1"
PROFILE_MANIFEST_SCHEMA = "pokemon.red.acquisition-replanning-profile-lineage.v1"
SOURCE_PROFILE_MANIFEST_SCHEMA = (
    "pokemon.red.acquisition-replanning-source-profile-manifest.v1"
)
SOURCE_PROFILE_MANIFEST_PATH = (
    PROJECT_ROOT / "configs/acquisition-replanning-source-profile-manifest-v1.json"
)
APPROVED_SOURCE_PLAN_SHA256 = (
    "74a89eafd467e44ca41ad262e5ddc40ec22a05f8368aa08487af6d139061a548"
)
APPROVED_PRIOR_CAMPAIGN_SHA256 = (
    "452cff2afa25278900334b8c0e69583a0c511e943ef727593fed938653f995b9",
)
APPROVED_PAIRED_PLAN_SHA256 = (
    "c38ebd8b3241bebff8491c59b846b6b24f66fc6d2c1c4feda79d0f916766dfb5"
)
APPROVED_CONTEXT_CATALOG_SHA256 = (
    "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_MAX_BYTES = 4 * 1024 * 1024


class AcquisitionReplanningPlanError(RuntimeError):
    """Raised before a private profile transformation can publish partial output."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--expected-source-plan-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--prior-campaign", type=Path, action="append", required=True)
    parser.add_argument(
        "--expected-prior-campaign-sha256", action="append", required=True
    )
    parser.add_argument("--paired-plan", type=Path, required=True)
    parser.add_argument("--expected-paired-plan-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    provenance = _source_attestation(args)
    (
        source_plan_sha256,
        context_catalog_sha256,
        prior_expected,
        paired_plan_sha256,
    ) = _approved_inputs(args)
    source = _document(
        args.source_plan,
        expected_sha256=source_plan_sha256,
        subject="source plan",
    )
    if set(source) != {"entries", "registry_sha256", "schema", "source_commit"} or (
        source.get("schema") != PLAN_SCHEMA
    ):
        raise AcquisitionReplanningPlanError("source plan authentication")
    source_commit = _text(source.get("source_commit"), "source commit")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        source_commit,
    )
    if source.get("registry_sha256") != registry.registry_sha256:
        raise AcquisitionReplanningPlanError("source plan authentication")
    entries = _entries(source, registry)
    catalog = _context_catalog(
        args.context_catalog,
        expected_sha256=context_catalog_sha256,
        registry=registry,
    )
    expected_profiles, source_profile_manifest_sha256 = _source_profile_manifest(
        registry,
        source_plan_sha256=source_plan_sha256,
    )
    expected_prior = args.expected_prior_campaign_sha256
    if len(args.prior_campaign) != len(expected_prior):
        raise AcquisitionReplanningPlanError("prior campaign binding")
    captures = _source_capture_index(entries, catalog)
    excluded: set[str] = set()
    prior_hashes: list[str] = []
    for path, expected in zip(args.prior_campaign, expected_prior, strict=True):
        campaign = _document(
            path,
            expected_sha256=expected,
            subject="prior campaign",
        )
        roots = _repeatable_roots(
            campaign,
            source_plan_sha256=source_plan_sha256,
        )
        for row in roots:
            if row.get("focus_kind") == GoalKind.ACQUIRE_SPECIES.value:
                excluded.add(_physical_slot(row, captures, subject="prior root"))
        prior_hashes.append(_sha(expected, "prior campaign"))
    paired = _document(
        args.paired_plan,
        expected_sha256=paired_plan_sha256,
        subject="paired plan",
    )
    paired_root = _paired_root(
        paired,
        source_plan_sha256=source_plan_sha256,
    )
    if paired_root.get("focus_kind") != GoalKind.ACQUIRE_SPECIES.value:
        raise AcquisitionReplanningPlanError("paired root authentication")
    excluded.add(_physical_slot(paired_root, captures, subject="paired root"))
    if len(excluded) != 2:
        raise AcquisitionReplanningPlanError("prior acquisition denominator")

    claim_registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
        eligible = tuple(
            entry
            for entry in entries
            if (
                (
                    assignment := registry.assignment(
                        _text(entry.get("slot_id"), "slot")
                    )
                ).partition
                == "train"
                and assignment.focus_kind is GoalKind.ACQUIRE_SPECIES
                and entry.get("slot_id") not in excluded
                and _root_is_open(entry, captures, claim_registry)
            )
        )
        if len(eligible) != 4:
            raise AcquisitionReplanningPlanError("unused acquisition denominator")

        output_root = _new_output_root(args.output_root)
        profiles_root = output_root / "profiles"
        try:
            profiles_root.mkdir(mode=0o700)
            output_entries: list[dict[str, str]] = []
            extended_ids = {_text(entry.get("slot_id"), "slot") for entry in eligible}
            profile_hashes: list[str] = []
            profile_lineage: list[dict[str, object]] = []
            for entry in entries:
                slot_id = _text(entry.get("slot_id"), "slot")
                source_profile = _external_regular(
                    Path(_text(entry.get("profile"), "profile"))
                )
                source_payload = source_profile.read_bytes()
                source_profile_sha256 = hashlib.sha256(source_payload).hexdigest()
                expected_profile_sha256 = expected_profiles.get(slot_id)
                if (
                    expected_profile_sha256 is not None
                    and source_profile_sha256 != expected_profile_sha256
                ):
                    raise AcquisitionReplanningPlanError(
                        "source profile authentication"
                    )
                payload = source_payload
                if slot_id in extended_ids:
                    payload = build_acquisition_replanning_profile_payload(
                        parse_red_goal_context_profile(payload)
                    )
                parsed = parse_red_goal_context_profile(payload)
                if parsed.profile_id != slot_id:
                    raise AcquisitionReplanningPlanError("profile identity")
                destination = profiles_root / f"{slot_id}.json"
                _write_exclusive(destination, payload)
                output_profile_sha256 = hashlib.sha256(payload).hexdigest()
                profile_hashes.append(output_profile_sha256)
                capture = captures[slot_id]
                profile_lineage.append(
                    {
                        "envelope_file_sha256": capture[3],
                        "output_profile_sha256": output_profile_sha256,
                        "slot_id": slot_id,
                        "source_profile_sha256": source_profile_sha256,
                        "state_file_sha256": capture[2],
                        "transformed": slot_id in extended_ids,
                    }
                )
                output_entries.append(
                    {
                        "envelope": _text(entry.get("envelope"), "envelope"),
                        "profile": str(destination),
                        "slot_id": slot_id,
                        "state": _text(entry.get("state"), "state"),
                    }
                )
            plan = {
                "entries": output_entries,
                "registry_sha256": registry.registry_sha256,
                "schema": PLAN_SCHEMA,
                "source_commit": source_commit,
            }
            plan_payload = _canonical_line(plan)
            plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
            manifest = {
                "builder_runner_sha256": provenance["runner_sha256"],
                "builder_source_bundle_sha256": provenance["source_bundle_sha256"],
                "builder_source_commit": provenance["source_commit"],
                "context_catalog_sha256": context_catalog_sha256,
                "entries": profile_lineage,
                "output_plan_sha256": plan_sha256,
                "paired_plan_sha256": paired_plan_sha256,
                "prior_campaign_sha256": list(prior_expected),
                "schema": PROFILE_MANIFEST_SCHEMA,
                "source_profile_manifest_sha256": source_profile_manifest_sha256,
                "source_plan_sha256": source_plan_sha256,
            }
            manifest_payload = _canonical_line(manifest)
            _write_exclusive(output_root / "plan.json", plan_payload)
            _write_exclusive(output_root / "profile-lineage.json", manifest_payload)
            _fsync_directory(profiles_root)
            _fsync_directory(output_root)
        except BaseException:
            # The new output root is never reused after an interrupted publication.
            raise
    return {
        "schema": "pokemon.red.acquisition-replanning-context-plan-build.v1",
        "status": "private_plan_created_without_prediction_or_action",
        "source_commit": provenance["source_commit"],
        "source_bundle_sha256": provenance["source_bundle_sha256"],
        "runner_sha256": provenance["runner_sha256"],
        "context_catalog_sha256": context_catalog_sha256,
        "source_plan_sha256": source_plan_sha256,
        "source_profile_manifest_sha256": source_profile_manifest_sha256,
        "prior_campaign_sha256": prior_hashes,
        "paired_plan_sha256": paired_plan_sha256,
        "output_plan_sha256": plan_sha256,
        "profile_lineage_manifest_sha256": hashlib.sha256(
            manifest_payload
        ).hexdigest(),
        "profile_set_sha256": _canonical_sha256(sorted(profile_hashes)),
        "contexts": len(output_entries),
        "excluded_used_acquisition_roots": len(excluded),
        "extended_unused_acquisition_roots": len(extended_ids),
        "completed_battles_per_development_dose": 4,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
    }


def _source_attestation(args: argparse.Namespace) -> dict[str, str]:
    _require_project_import_origins()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    commit = source.git_commit
    runner_path = Path(__file__).resolve()
    if (
        not isinstance(commit, str)
        or _GIT_COMMIT.fullmatch(commit) is None
        or runner_path.parent != (PROJECT_ROOT / "scripts").resolve()
    ):
        raise AcquisitionReplanningPlanError("source authentication")
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        args.expected_source_commit != commit
        or _GIT_COMMIT.fullmatch(args.expected_source_commit) is None
        or _sha(args.expected_source_bundle_sha256, "source bundle")
        != source_bundle_sha256
        or _sha(args.expected_runner_sha256, "runner") != runner_sha256
    ):
        raise AcquisitionReplanningPlanError("external executable attestation")
    return {
        "runner_sha256": runner_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "source_commit": commit,
    }


def _approved_inputs(
    args: argparse.Namespace,
) -> tuple[str, str, tuple[str, ...], str]:
    source = _sha(args.expected_source_plan_sha256, "source plan")
    catalog = _sha(args.expected_context_catalog_sha256, "context catalog")
    prior = tuple(
        _sha(value, "prior campaign")
        for value in args.expected_prior_campaign_sha256
    )
    paired = _sha(args.expected_paired_plan_sha256, "paired plan")
    if (
        source != APPROVED_SOURCE_PLAN_SHA256
        or catalog != APPROVED_CONTEXT_CATALOG_SHA256
        or prior != APPROVED_PRIOR_CAMPAIGN_SHA256
        or paired != APPROVED_PAIRED_PLAN_SHA256
    ):
        raise AcquisitionReplanningPlanError("approved predecessor binding")
    return source, catalog, prior, paired


def _context_catalog(
    path: Path,
    *,
    expected_sha256: str,
    registry: GoalManagerCollectionRegistry,
) -> GoalManagerContextCatalog:
    resolved = _external_regular(path)
    payload = resolved.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise AcquisitionReplanningPlanError("context catalog authentication")
    catalog = parse_goal_manager_context_catalog(payload, registry)
    if catalog.catalog_sha256 != expected_sha256:
        raise AcquisitionReplanningPlanError("context catalog authentication")
    return catalog


def _source_profile_manifest(
    registry: GoalManagerCollectionRegistry,
    *,
    source_plan_sha256: str,
) -> tuple[dict[str, str], str]:
    try:
        payload = SOURCE_PROFILE_MANIFEST_PATH.read_bytes()
    except OSError:
        raise AcquisitionReplanningPlanError(
            "source profile manifest authentication"
        ) from None
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AcquisitionReplanningPlanError(
            "source profile manifest authentication"
        ) from None
    if (
        not isinstance(value, dict)
        or _canonical_line(value) != payload
        or set(value) != {"profiles", "schema", "source_plan_sha256"}
        or value.get("schema") != SOURCE_PROFILE_MANIFEST_SCHEMA
        or value.get("source_plan_sha256") != source_plan_sha256
    ):
        raise AcquisitionReplanningPlanError("source profile manifest authentication")
    rows = value.get("profiles")
    if not isinstance(rows, list):
        raise AcquisitionReplanningPlanError("source profile manifest authentication")
    expected_slots = tuple(
        slot.slot_id
        for slot in registry.slots
        if (
            (assignment := registry.assignment(slot.slot_id)).partition == "train"
            and assignment.focus_kind is GoalKind.ACQUIRE_SPECIES
        )
    )
    profiles: dict[str, str] = {}
    for raw in rows:
        row = _mapping(raw, "source profile manifest")
        if set(row) != {"profile_sha256", "slot_id"}:
            raise AcquisitionReplanningPlanError(
                "source profile manifest authentication"
            )
        slot_id = _text(row.get("slot_id"), "source profile manifest")
        if slot_id in profiles:
            raise AcquisitionReplanningPlanError(
                "source profile manifest authentication"
            )
        profiles[slot_id] = _sha(
            row.get("profile_sha256"), "source profile manifest"
        )
    if tuple(profiles) != expected_slots:
        raise AcquisitionReplanningPlanError("source profile manifest authentication")
    return profiles, hashlib.sha256(payload).hexdigest()


_ROOT_KEYS = {
    "assignment_id",
    "available_goal_kinds",
    "available_menu_sha256",
    "binding_manifest_sha256",
    "capture_id",
    "entry_index",
    "envelope_file_sha256",
    "envelope_sha256",
    "focus_kind",
    "policy_context_sha256",
    "profile_file_sha256",
    "question_sha256",
    "root_lineage_id",
    "state_file_sha256",
    "state_sha256",
}


def _repeatable_roots(
    campaign: Mapping[str, object],
    *,
    source_plan_sha256: str,
) -> tuple[Mapping[str, object], ...]:
    expected_keys = {
        "campaign_id",
        "candidate",
        "context_plan_sha256",
        "numpy_runtime_sha256",
        "outcome_objective",
        "private_root_identity_sha256",
        "roots",
        "runner_sha256",
        "runtime_sha256",
        "schema",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
        "trials",
    }
    roots_raw = campaign.get("roots")
    trials_raw = campaign.get("trials")
    if (
        set(campaign) != expected_keys
        or campaign.get("schema") != REPEATABLE_SCHEMA
        or campaign.get("context_plan_sha256") != source_plan_sha256
        or not isinstance(roots_raw, list)
        or not isinstance(trials_raw, list)
    ):
        raise AcquisitionReplanningPlanError("prior campaign authentication")
    identity = dict(campaign)
    campaign_id = identity.pop("campaign_id", None)
    stripped_trials: list[dict[str, object]] = []
    for value in trials_raw:
        trial = _mapping(value, "prior trial")
        stripped = dict(trial)
        stripped.pop("episode_id", None)
        stripped.pop("trial_claim_sha256", None)
        stripped_trials.append(stripped)
    identity["trials"] = stripped_trials
    if campaign_id != _canonical_sha256(identity):
        raise AcquisitionReplanningPlanError("prior campaign authentication")
    roots = tuple(_mapping(value, "prior root") for value in roots_raw)
    for root in roots:
        _validate_root_record(root, subject="prior root")
    return roots


def _paired_root(
    paired: Mapping[str, object],
    *,
    source_plan_sha256: str,
) -> Mapping[str, object]:
    expected_keys = {
        "arms",
        "base",
        "behavior",
        "candidate",
        "context_plan_sha256",
        "development_runner_sha256",
        "endpoint",
        "numpy_runtime_sha256",
        "prior_campaign_sha256",
        "private_root_identity_sha256",
        "root",
        "root_consumption_sha256",
        "runner_sha256",
        "runtime_sha256",
        "schema",
        "screen_id",
        "selection",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
    }
    if (
        set(paired) != expected_keys
        or paired.get("schema") != PAIRED_SCHEMA
        or paired.get("context_plan_sha256") != source_plan_sha256
    ):
        raise AcquisitionReplanningPlanError("paired plan authentication")
    identity = dict(paired)
    screen_id = identity.pop("screen_id", None)
    identity.pop("arms", None)
    if screen_id != _canonical_sha256(identity):
        raise AcquisitionReplanningPlanError("paired plan authentication")
    root = _mapping(paired.get("root"), "paired root")
    _validate_root_record(root, subject="paired root")
    if paired.get("root_consumption_sha256") != root_consumption_sha256(
        state_sha256=_sha(root.get("state_sha256"), "paired root state"),
        envelope_sha256=_sha(root.get("envelope_sha256"), "paired root envelope"),
    ):
        raise AcquisitionReplanningPlanError("paired plan authentication")
    return root


def _validate_root_record(root: Mapping[str, object], *, subject: str) -> None:
    if set(root) != _ROOT_KEYS:
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    assignment = _sha(root.get("assignment_id"), subject)
    if root.get("root_lineage_id") != f"red-goal-root-{assignment}":
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    capture_id = _text(root.get("capture_id"), subject)
    if _SAFE_ID.fullmatch(capture_id) is None:
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    if not isinstance(root.get("entry_index"), int) or isinstance(
        root.get("entry_index"), bool
    ):
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    available = root.get("available_goal_kinds")
    if (
        not isinstance(available, list)
        or any(not isinstance(value, str) for value in available)
    ):
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    for key in _ROOT_KEYS - {
        "available_goal_kinds",
        "capture_id",
        "entry_index",
        "focus_kind",
        "root_lineage_id",
    }:
        _sha(root.get(key), subject)


def _source_capture_index(
    entries: tuple[Mapping[str, object], ...],
    catalog: GoalManagerContextCatalog,
) -> dict[str, tuple[str, str, str, str]]:
    captures: dict[str, tuple[str, str, str, str]] = {}
    states: set[str] = set()
    envelopes: set[str] = set()
    for entry in entries:
        slot_id = _text(entry.get("slot_id"), "slot")
        state_path = _external_regular(Path(_text(entry.get("state"), "state")))
        envelope_path = _external_regular(
            Path(_text(entry.get("envelope"), "envelope"))
        )
        state_bytes = state_path.read_bytes()
        envelope_bytes = envelope_path.read_bytes()
        capture = parse_goal_manager_context_capture(state_bytes, envelope_bytes)
        catalog_entry = catalog.entry(slot_id)
        if (
            capture.capture_id != slot_id
            or capture.capture_id != catalog_entry.capture_id
            or capture.state_sha256 != catalog_entry.state_sha256
            or capture.envelope_sha256 != catalog_entry.envelope_sha256
            or capture.state_sha256 in states
            or capture.envelope_sha256 in envelopes
        ):
            raise AcquisitionReplanningPlanError("source capture authentication")
        states.add(capture.state_sha256)
        envelopes.add(capture.envelope_sha256)
        captures[slot_id] = (
            capture.state_sha256,
            capture.envelope_sha256,
            hashlib.sha256(state_bytes).hexdigest(),
            hashlib.sha256(envelope_bytes).hexdigest(),
        )
    return captures


def _physical_slot(
    root: Mapping[str, object],
    captures: Mapping[str, tuple[str, str, str, str]],
    *,
    subject: str,
) -> str:
    key = (
        _sha(root.get("state_sha256"), subject),
        _sha(root.get("envelope_sha256"), subject),
    )
    matches = tuple(
        slot_id for slot_id, capture in captures.items() if capture[:2] == key
    )
    if len(matches) != 1 or root.get("capture_id") != matches[0]:
        raise AcquisitionReplanningPlanError(f"{subject} physical identity")
    return matches[0]


def _root_is_open(
    entry: Mapping[str, object],
    captures: Mapping[str, tuple[str, str, str, str]],
    registry: Path,
) -> bool:
    state_sha256, envelope_sha256, _state_file, _envelope_file = captures[
        _text(entry.get("slot_id"), "slot")
    ]
    return root_claim_is_available(
        registry,
        root_consumption_sha256(
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
        ),
    )


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise AcquisitionReplanningPlanError("source authentication")
    package_root = (_BOOTSTRAP_SRC / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith(
            "pokemon_red_completion."
        ):
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise AcquisitionReplanningPlanError("source authentication")
        path = Path(raw)
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError:
            raise AcquisitionReplanningPlanError("source authentication") from None
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or not resolved.is_relative_to(package_root)
        ):
            raise AcquisitionReplanningPlanError("source authentication")


def _entries(
    document: Mapping[str, object],
    registry: GoalManagerCollectionRegistry,
) -> tuple[Mapping[str, object], ...]:
    raw = document.get("entries")
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        raise AcquisitionReplanningPlanError("source plan entries")
    entries = tuple(cast(Mapping[str, object], item) for item in raw)
    expected_ids = tuple(slot.slot_id for slot in registry.slots)
    if tuple(_text(entry.get("slot_id"), "slot") for entry in entries) != expected_ids:
        raise AcquisitionReplanningPlanError("source plan registry order")
    for entry in entries:
        if set(entry) != {"envelope", "profile", "slot_id", "state"}:
            raise AcquisitionReplanningPlanError("source plan entry fields")
        for key in ("envelope", "profile", "state"):
            _external_regular(Path(_text(entry.get(key), key)))
    return entries


def _document(path: Path, *, expected_sha256: object, subject: str) -> dict[str, object]:
    resolved = _external_regular(path)
    payload = resolved.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _sha(expected_sha256, subject):
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    if not payload or len(payload) > _MAX_BYTES:
        raise AcquisitionReplanningPlanError(f"{subject} size")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AcquisitionReplanningPlanError(f"{subject} canonical JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise AcquisitionReplanningPlanError(f"{subject} canonical JSON")
    return value


def _new_output_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()) or resolved.exists():
        raise AcquisitionReplanningPlanError("output root must be new and external")
    parent = resolved.parent
    if not parent.is_dir():
        raise AcquisitionReplanningPlanError("output parent is unavailable")
    resolved.mkdir(mode=0o700)
    return resolved


def _external_regular(path: Path) -> Path:
    resolved = path.resolve()
    try:
        metadata = path.lstat()
    except OSError:
        raise AcquisitionReplanningPlanError("private input unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
    ):
        raise AcquisitionReplanningPlanError("private input location")
    return resolved


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with suppress(OSError):
            path.unlink()
        raise


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_line(value)).hexdigest()


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    return value


def _sha(value: object, subject: str) -> str:
    result = _text(value, subject)
    if _SHA256.fullmatch(result) is None:
        raise AcquisitionReplanningPlanError(f"{subject} authentication")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (
        AcquisitionReplanningPlanError,
        CollectionProtocolError,
        EvaluationIdentityError,
        FreshCompositionQualificationError,
        GoalManagerContextCatalogError,
        GoalManagerProtocolError,
        OSError,
        RedGoalContextProfileError,
        ValueError,
    ):
        parser.error(
            "Acquisition-replanning context-plan build failed closed; "
            "private details were withheld."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
