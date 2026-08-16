#!/usr/bin/env python3
"""Show the honest Red completion-aware party-learning readiness gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import time
import webbrowser
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
)
from pokemon_red_completion.party_development_outcome_results import (  # noqa: E402
    PartyDevelopmentOutcomeTrialResult,
    parse_party_development_trial_terminal,
)
from pokemon_red_completion.party_development_readiness_dashboard import (  # noqa: E402
    party_development_readiness_dashboard_snapshot,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PRIVATE_ROOT_SENTINEL,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import OutcomeEvidenceStatus  # noqa: E402

EVIDENCE_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "party-development-v2-readiness-2026-08-16.json"
)
V4_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-pp-materialization-v4-preflight-2026-08-16.json"
)
V4_EVIDENCE_SCHEMA = "pokemon.red.party-development-pp-materialization-v4-preflight-evidence.v1"
CATALOG_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-frozen-input-catalog-v1-result-2026-08-16.json"
)
CATALOG_EVIDENCE_SCHEMA = "pokemon.red.party-development-frozen-input-catalog-v1-result.v1"
CATALOG_AUDIT_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-frozen-input-catalog-v1-audit-2026-08-16.json"
)
CATALOG_AUDIT_EVIDENCE_SCHEMA = "pokemon.red.party-development-frozen-input-catalog-v1-audit.v1"
# Keep the readiness view separate from both the historical Pokémon dashboard
# (8765) and an existing local dashboard already using 8766 on the owner host.
DEFAULT_READINESS_PORT = DASHBOARD_DEFAULT_PORT + 2
_LIVE_STREAM_MAX_BYTES = 1024 * 1024
_LIVE_PARTITIONS = ("train", "development")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_CAMPAIGN_PLAN_BYTES = 8 * 1024 * 1024
_CAMPAIGN_CLAIM_KIND = "party_development_outcome_claim"
_CAMPAIGN_TERMINAL_KIND = "party_development_outcome_terminal"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_READINESS_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--private-artifact-root", type=Path)
    parser.add_argument("--partition", choices=_LIVE_PARTITIONS, default="train")
    parser.add_argument("--campaign-plan", type=Path)
    parser.add_argument("--campaign-plan-file-sha256")
    return parser


def _load_evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("party-development readiness evidence must be a JSON object")
    return value


def _load_v4_evidence() -> dict[str, object]:
    value = json.loads(V4_EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("PP v4 preflight evidence must be a JSON object")
    return value


def _load_catalog_evidence() -> dict[str, object]:
    value = json.loads(CATALOG_EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("frozen catalog evidence must be a JSON object")
    return value


def _load_catalog_audit_evidence() -> dict[str, object]:
    value = json.loads(CATALOG_AUDIT_EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("frozen catalog audit evidence must be a JSON object")
    return value


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"PP v4 {key.replace('_', ' ')} is invalid")
    return value


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _load_campaign_plan(
    path: Path | None,
    expected_file_sha256: str | None,
) -> PartyDevelopmentOutcomeCampaignPlan | None:
    if path is None and expected_file_sha256 is None:
        return None
    if path is None or expected_file_sha256 is None:
        raise ProgressDashboardError(
            "dashboard campaign plan and file digest must be supplied together"
        )
    if (
        not path.is_absolute()
        or path.resolve().is_relative_to(PROJECT_ROOT.resolve())
        or _SHA256.fullmatch(expected_file_sha256) is None
    ):
        raise ProgressDashboardError("dashboard campaign plan identity is invalid")
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise ProgressDashboardError("dashboard campaign plan is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not payload
        or len(payload) > _MAX_CAMPAIGN_PLAN_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_file_sha256
    ):
        raise ProgressDashboardError("dashboard campaign plan bytes are invalid")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
        plan = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ProgressDashboardError("dashboard campaign plan is invalid") from None
    return plan


def _current_snapshot(
    readiness: Mapping[str, object],
    v4_evidence: Mapping[str, object],
):
    base = party_development_readiness_dashboard_snapshot(readiness)
    if (
        v4_evidence.get("schema") != V4_EVIDENCE_SCHEMA
        or v4_evidence.get("status") != "ready_for_one_partition_owner_authorization"
    ):
        raise ProgressDashboardError("PP v4 preflight evidence is unsupported")
    source = _mapping(v4_evidence, "execution_source")
    packet = _mapping(v4_evidence, "immutable_packet")
    preflight = _mapping(v4_evidence, "read_only_preflight")
    audit = _mapping(v4_evidence, "independent_audit")
    authorization = _mapping(v4_evidence, "authorization")
    source_commit = source.get("git_commit")
    ci_run = source.get("github_ci_run")
    ci_attempt = source.get("github_ci_attempt")
    plan_file_sha256 = packet.get("private_plan_file_sha256")
    maximum_battles = packet.get("maximum_completed_battles")
    minimum_headroom = packet.get("minimum_battle_headroom")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or not isinstance(ci_run, int)
        or isinstance(ci_run, bool)
        or ci_run <= 0
        or not isinstance(ci_attempt, int)
        or isinstance(ci_attempt, bool)
        or ci_attempt <= 0
        or source.get("github_ci_conclusion") != "success"
        or not isinstance(plan_file_sha256, str)
        or len(plan_file_sha256) != 64
        or maximum_battles != 32
        or minimum_headroom != 5
        or preflight.get("train_status") != "ready_authorization_required"
        or preflight.get("development_status") != "ready_authorization_required"
        or preflight.get("controller_actions") != 0
        or preflight.get("teacher_queries") != 0
        or preflight.get("model_predictions") != 0
        or preflight.get("learner_outcomes_opened") != 0
        or preflight.get("materializations_completed") != 0
        or audit.get("verdict") != "approve_request_for_exactly_one_named_partition"
        or authorization.get("granted") is not False
        or authorization.get("authorized_partition") is not None
    ):
        raise ProgressDashboardError("PP v4 readiness evidence is inconsistent")

    retained_events = tuple(
        event
        for event in base.events
        if not event.startswith("Per-source hard bounds") and not event.startswith("Next:")
    )
    return replace(
        base,
        message=(
            "V4 is frozen and both natural middle-PP sources pass read-only preflight. "
            "Claude approved asking for one partition; train still requires exact owner authority."
        ),
        location="Natural PP preparation gate · train authorization pending",
        events=(
            (
                f"V4 packet verified · source {source_commit[:7]} · CI {ci_run} "
                f"attempt {ci_attempt} · plan {plan_file_sha256[:8]}…"
            ),
            "Read-only preflights 2/2 · Claude APPROVE to ask · controller actions 0",
            *retained_events,
            (
                f"Per-source hard bounds · battles {maximum_battles} · minimum headroom "
                f"{minimum_headroom} · encounter steps 10000 · actions 250000 · frames 5000000"
            ),
            (
                "Next: exact owner authorization for train once; development remains separate, "
                "then freeze and review the 8+6 catalog"
            ),
        ),
    )


def _require_monitor_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    if not path.is_absolute():
        raise ProgressDashboardError("dashboard private artifact root must be absolute")
    try:
        metadata = path.lstat()
        sentinel = (path / PRIVATE_ROOT_SENTINEL).lstat()
    except OSError:
        raise ProgressDashboardError("dashboard private artifact root is unavailable") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(sentinel.st_mode)
        or stat.S_ISLNK(sentinel.st_mode)
    ):
        raise ProgressDashboardError("dashboard private artifact root is invalid")
    return path


def _artifact_directory(root: Path, partition: str) -> Path | None:
    if partition not in _LIVE_PARTITIONS:
        raise ProgressDashboardError("dashboard PP partition is invalid")
    artifact_id = f"red-party-pp-materialization-v1-{partition}"
    existing: list[Path] = []
    for candidate in (
        root / f"{artifact_id}.partial",
        root / artifact_id,
        root / f"{artifact_id}.failed.partial",
    ):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise ProgressDashboardError("dashboard PP artifact cannot be inspected") from None
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise ProgressDashboardError("dashboard PP artifact is invalid")
        existing.append(candidate)
    if len(existing) > 1:
        raise ProgressDashboardError("dashboard PP artifact identity is ambiguous")
    return existing[0] if existing else None


def _latest_stream_record(
    directory: Path,
    stream: str,
    *,
    expected_record_type: str,
) -> dict[str, object] | None:
    path = directory / f"{stream}.jsonl"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise ProgressDashboardError("dashboard PP stream cannot be inspected") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_size > _LIVE_STREAM_MAX_BYTES
    ):
        raise ProgressDashboardError("dashboard PP stream is invalid")
    try:
        payload = path.read_bytes()
    except OSError:
        raise ProgressDashboardError("dashboard PP stream cannot be read") from None
    lines = payload.split(b"\n")
    if payload and not payload.endswith(b"\n"):
        lines = lines[:-1]
    for line in reversed(lines):
        if not line:
            continue
        try:
            value = json.loads(line.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProgressDashboardError("dashboard PP stream record is invalid") from None
        if not isinstance(value, dict):
            raise ProgressDashboardError("dashboard PP stream record is invalid")
        if value.get("record_type") != expected_record_type or value.get("schema_version") != 1:
            raise ProgressDashboardError("dashboard PP stream record is unsupported")
        return value
    return None


def _live_artifact_record(
    root: Path,
    partition: str,
) -> tuple[str, dict[str, object] | None]:
    directory = _artifact_directory(root, partition)
    if directory is None:
        return "waiting", None
    failure = _latest_stream_record(
        directory,
        "failure",
        expected_record_type="party_development_pp_materialization_failure",
    )
    if failure is not None:
        return "failed", failure
    terminal = _latest_stream_record(
        directory,
        "terminal",
        expected_record_type="party_development_pp_materialization_terminal",
    )
    if terminal is not None:
        return "passed", terminal
    progress = _latest_stream_record(
        directory,
        "progress",
        expected_record_type="party_development_pp_materialization_progress",
    )
    if progress is not None:
        return "running", progress
    return "claimed", None


def _record_count(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"dashboard PP {key.replace('_', ' ')} is invalid")
    return value


def _receipt_digest(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProgressDashboardError(f"dashboard catalog {key.replace('_', ' ')} is invalid")
    return value


def _catalog_snapshot(
    base: DashboardSnapshot,
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    if (
        evidence.get("schema") != CATALOG_EVIDENCE_SCHEMA
        or evidence.get("status") != "exact_inputs_frozen_outcomes_closed"
        or evidence.get("private_path_fields") != 0
    ):
        raise ProgressDashboardError("frozen catalog evidence is unsupported")
    catalog = _mapping(evidence, "catalog")
    freeze = _mapping(evidence, "freeze_identity")
    inputs = _mapping(evidence, "input_lineage")
    interpretation = _mapping(evidence, "interpretation")
    protected = _mapping(evidence, "protected_access")
    partition_counts = _mapping(catalog, "partition_counts")
    choice_counts = _mapping(catalog, "choice_kind_partition_counts")
    width_counts = _mapping(catalog, "available_width_partition_counts")
    source_commit = freeze.get("source_commit")
    ci_run = freeze.get("exact_ci_run")
    ci_attempt = freeze.get("exact_ci_attempt")
    protected_keys = (
        "answers_selected",
        "controller_actions",
        "crystal_cases_opened",
        "model_predictions",
        "model_updates",
        "outcomes_opened",
        "sealed_red_cases_opened",
        "teacher_queries",
    )
    if (
        catalog.get("question_count") != 14
        or partition_counts != {"development": 6, "train": 8}
        or choice_counts
        != {
            "development:trainee": 3,
            "development:venue": 3,
            "train:trainee": 4,
            "train:venue": 4,
        }
        or width_counts
        != {
            "development:2": 3,
            "development:5": 1,
            "development:6": 2,
            "train:2": 4,
            "train:6": 4,
        }
        or catalog.get("prepared_context_count") != 2
        or inputs.get("historical_checkpoint_count") != 81
        or inputs.get("new_prepared_checkpoint_count") != 2
        or inputs.get("re_inventory_checkpoint_count") != 83
        or not isinstance(source_commit, str)
        or _GIT_COMMIT.fullmatch(source_commit) is None
        or type(ci_run) is not int  # noqa: E721
        or ci_run <= 0
        or type(ci_attempt) is not int  # noqa: E721
        or ci_attempt <= 0
        or freeze.get("exact_ci_conclusion") != "success"
        or interpretation.get("candidate_menus_frozen") != 14
        or interpretation.get("learner_outcomes_created") != 0
        or interpretation.get("training_examples_created") != 0
        or interpretation.get("model_fit") is not False
        or interpretation.get("authority_promoted") is not False
        or any(protected.get(key) != 0 for key in protected_keys)
    ):
        raise ProgressDashboardError("frozen catalog evidence is inconsistent")
    catalog_sha256 = _receipt_digest(catalog, "catalog_sha256")
    prospective_sha256 = _receipt_digest(catalog, "prospective_catalog_sha256")
    _receipt_digest(catalog, "catalog_file_sha256")
    _receipt_digest(catalog, "summary_file_sha256")
    _receipt_digest(freeze, "source_bundle_sha256")
    return replace(
        base,
        run_status="waiting",
        stage="Completion-aware party learner · frozen-input review gate",
        stage_progress=1.0,
        actions=0,
        frame_count=0,
        message=(
            "Fourteen completion-aware Red questions are frozen: 8 train and 6 untouched "
            "development. Outcomes remain 0/14 and model fitting has not begun."
        ),
        location="Frozen 8+6 catalog · independent input review pending",
        events=(
            "Official input catalog frozen · 14 questions · 8 train / 6 development",
            "Choice coverage · train 4 trainee + 4 venue · development 3 + 3",
            "Available candidate widths · 2, 5 and 6 · every question has at least 2",
            "Natural middle-PP preparations 2/2 · historical captures 81 + prepared 2",
            (f"Catalog {catalog_sha256[:8]}… · prospective {prospective_sha256[:8]}…"),
            f"Published freezer {source_commit[:7]} · CI {ci_run} attempt {ci_attempt}",
            "Compatible venue priors 2/2 · both frozen before question construction",
            "Goal coverage · balance, collection, evolution and role coverage in both partitions",
            "Answers 0/14 · teacher queries 0 · predictions 0 · model updates 0",
            "Sealed Red 0 · Crystal 0 · full-game replays 0 · authority zero",
            (
                "Transfer target · validate the shared representation in Crystal before "
                "expanding toward the cross-game living Pokédex"
            ),
            (
                "Next: independent input-integrity review, then separately authorize 8+6 "
                "outcomes and one train-only fit"
            ),
        ),
    )


def _audited_catalog_snapshot(
    base: DashboardSnapshot,
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    if (
        evidence.get("schema") != CATALOG_AUDIT_EVIDENCE_SCHEMA
        or evidence.get("status") != "input_integrity_verified_outcomes_closed"
    ):
        raise ProgressDashboardError("frozen catalog audit evidence is unsupported")
    audit = _mapping(evidence, "audit_identity")
    catalog = _mapping(evidence, "catalog")
    reconstruction = _mapping(evidence, "reconstruction")
    acceptance = _mapping(evidence, "acceptance")
    mutations = _mapping(evidence, "mutation_audit")
    interpretation = _mapping(evidence, "interpretation")
    privacy = _mapping(evidence, "privacy")
    protected = _mapping(evidence, "protected_access")
    source_commit = audit.get("source_commit")
    ci_run = audit.get("exact_ci_run")
    ci_attempt = audit.get("exact_ci_attempt")
    script_sha256 = audit.get("audit_script_sha256")
    zero_keys = (
        "answers_selected",
        "controller_actions",
        "crystal_cases_opened",
        "model_predictions",
        "model_updates",
        "outcomes_opened",
        "sealed_red_cases_opened",
        "teacher_queries",
    )
    acceptance_keys = (
        "all_candidate_menus_reconstructed",
        "all_capture_envelope_joins_reconstructed",
        "all_reservation_joins_reconstructed",
        "all_root_lineages_reconstructed",
        "all_source_profile_joins_reconstructed",
        "committed_catalog_source_reproduced",
        "input_files_unchanged",
        "path_and_target_scan_clean",
        "rom_adjacent_artifacts_unchanged",
    )
    if (
        not isinstance(source_commit, str)
        or _GIT_COMMIT.fullmatch(source_commit) is None
        or type(ci_run) is not int  # noqa: E721
        or ci_run <= 0
        or type(ci_attempt) is not int  # noqa: E721
        or ci_attempt <= 0
        or audit.get("exact_ci_conclusion") != "success"
        or not isinstance(script_sha256, str)
        or _SHA256.fullmatch(script_sha256) is None
        or catalog.get("question_count") != 14
        or catalog.get("candidate_row_count") != 55
        or catalog.get("feature_column_count") != 66
        or catalog.get("nonconstant_feature_column_count") != 49
        or catalog.get("distinct_candidate_menu_count") != 12
        or catalog.get("partition_counts") != {"development": 6, "train": 8}
        or catalog.get("prepared_partition_counts") != {"development": 1, "train": 1}
        or any(
            reconstruction.get(key) != 14
            for key in (
                "candidate_feature_menus",
                "capture_envelope_joins",
                "reservation_joins",
                "root_lineages",
                "source_profile_joins",
            )
        )
        or reconstruction.get("historical_checkpoint_count") != 81
        or reconstruction.get("new_prepared_checkpoint_count") != 2
        or reconstruction.get("re_inventory_checkpoint_count") != 83
        or any(acceptance.get(key) is not True for key in acceptance_keys)
        or mutations.get("targeted_rejection_probes") != 21
        or mutations.get("targeted_rejection_probes_rejected") != 21
        or mutations.get("full_catalog_rehashed_forgery_probes") != 2
        or mutations.get("full_catalog_rehashed_forgery_probes_rejected") != 2
        or privacy.get("private_path_fields") != 0
        or privacy.get("candidate_feature_values_public") is not False
        or privacy.get("capture_identity_public") is not False
        or privacy.get("profile_identity_public") is not False
        or any(protected.get(key) != 0 for key in zero_keys)
        or protected.get("authority_promoted") is not False
        or interpretation.get("outcome_collection_authorized") is not False
        or interpretation.get("model_fit") is not False
        or interpretation.get("authority_promoted") is not False
    ):
        raise ProgressDashboardError("frozen catalog audit evidence is inconsistent")
    catalog_sha256 = _receipt_digest(catalog, "catalog_sha256")
    prospective_sha256 = _receipt_digest(catalog, "prospective_catalog_sha256")
    return replace(
        base,
        run_status="waiting",
        stage="Completion-aware party learner · bounded collector build",
        stage_progress=1.0,
        actions=0,
        frame_count=0,
        message=(
            "All fourteen frozen Red questions independently reconstruct. They require 55 cloned "
            "candidate trials; the catalog-wide collector is not yet published or authorized."
        ),
        location="Verified 8+6 inputs · 55-trial collector build",
        events=(
            "Input-integrity audit passed · all 14 reservation/state/profile/root/menu joins",
            "Dataset shape · 55 candidate rows · 66 features · 49 varying · 12 distinct menus",
            "Partition isolation · 8 train / 6 untouched development · prepared contexts 1 + 1",
            "Attack set · 19/19 boundary probes rejected · 2/2 re-hashed forgeries rejected",
            f"Catalog {catalog_sha256[:8]}… · prospective {prospective_sha256[:8]}…",
            f"Published verifier {source_commit[:7]} · CI {ci_run} attempt {ci_attempt}",
            f"Verifier script {script_sha256[:8]}… · protected inputs unchanged",
            "Required outcome units · 14 complete examples · 55 cloned candidate trials",
            "Answers 0/14 · trials 0/55 · complete examples 0/14 · teacher 0 · controller 0",
            "Predictions 0 · model updates 0 · fits 0 · live authority zero",
            "Sealed Red 0 · Crystal 0 · full-game replays 0",
            (
                "Next: build, attack, publish and read-only preflight the 55-trial collector; "
                "only then request exact owner authorization"
            ),
        ),
    )


def _campaign_records(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    store: PrivateArtifactRoot | None,
) -> tuple[
    dict[str, PartyDevelopmentOutcomeTrialClaim],
    dict[str, PartyDevelopmentOutcomeTrialResult],
]:
    claims: dict[str, PartyDevelopmentOutcomeTrialClaim] = {}
    terminals: dict[str, PartyDevelopmentOutcomeTrialResult] = {}
    if store is None:
        return claims, terminals
    for assignment in plan.assignments:
        claim_record = store.find_sealed_record(
            f"{assignment.trial_id}-claim",
            expected_kind=_CAMPAIGN_CLAIM_KIND,
        )
        terminal_record = store.find_sealed_record(
            f"{assignment.trial_id}-terminal",
            expected_kind=_CAMPAIGN_TERMINAL_KIND,
        )
        claim: PartyDevelopmentOutcomeTrialClaim | None = None
        if claim_record is not None:
            claim = PartyDevelopmentOutcomeTrialClaim.from_private_dict(
                claim_record.read()
            )
            if claim != PartyDevelopmentOutcomeTrialClaim.build(plan, assignment):
                raise ProgressDashboardError(
                    "dashboard campaign claim differs from its frozen assignment"
                )
            claims[assignment.assignment_sha256] = claim
        if terminal_record is not None:
            if claim is None:
                raise ProgressDashboardError(
                    "dashboard campaign terminal exists without its durable claim"
                )
            terminal = parse_party_development_trial_terminal(terminal_record.read())
            terminal.require_within_plan(plan, assignment)
            terminals[assignment.assignment_sha256] = terminal
    return claims, terminals


def _campaign_snapshot(
    base: DashboardSnapshot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    store: PrivateArtifactRoot | None,
) -> DashboardSnapshot:
    claims, terminals = _campaign_records(plan, store)
    open_claims = set(claims) - set(terminals)
    if len(open_claims) > 1:
        raise ProgressDashboardError(
            "dashboard campaign has more than one claimed nonterminal trial"
        )
    assignments_by_scenario: dict[
        str, list[PartyDevelopmentOutcomeTrialAssignment]
    ] = {}
    for assignment in plan.assignments:
        assignments_by_scenario.setdefault(assignment.scenario_id, []).append(
            assignment
        )
    complete_scenarios: set[str] = set()
    for scenario_id, assignments in assignments_by_scenario.items():
        results = tuple(
            terminals.get(assignment.assignment_sha256)
            for assignment in assignments
        )
        if results and all(
            result is not None and result.status is OutcomeEvidenceStatus.MEASURED
            for result in results
        ):
            complete_scenarios.add(scenario_id)
    train_complete = sum(
        scenario_id in complete_scenarios
        and assignments[0].partition is ScenarioPartition.TRAIN
        for scenario_id, assignments in assignments_by_scenario.items()
    )
    development_complete = sum(
        scenario_id in complete_scenarios
        and assignments[0].partition is ScenarioPartition.DEVELOPMENT
        for scenario_id, assignments in assignments_by_scenario.items()
    )
    question_claims = {
        assignment.scenario_id
        for assignment in plan.assignments
        if assignment.assignment_sha256 in claims
    }
    measured = sum(
        result.status is OutcomeEvidenceStatus.MEASURED
        for result in terminals.values()
    )
    invalid = sum(
        result.status is OutcomeEvidenceStatus.INVALID
        for result in terminals.values()
    )
    censored = sum(
        result.status is OutcomeEvidenceStatus.CENSORED
        for result in terminals.values()
    )
    controller_actions = sum(
        result.controller_actions or 0 for result in terminals.values()
    )
    frames = sum(result.frames_executed or 0 for result in terminals.values())
    battles = sum(result.battles_completed or 0 for result in terminals.values())
    encounter_steps = sum(
        result.encounter_steps or 0 for result in terminals.values()
    )
    healing_trips = sum(result.healing_trips or 0 for result in terminals.values())
    rotations = sum(
        result.rotations_executed or 0 for result in terminals.values()
    )
    current = next(
        (
            assignment
            for assignment in plan.assignments
            if assignment.assignment_sha256 in open_claims
        ),
        None,
    )
    next_unclaimed = next(
        (
            assignment
            for assignment in plan.assignments
            if assignment.assignment_sha256 not in claims
        ),
        None,
    )
    claimed = len(claims)
    terminal_count = len(terminals)
    complete_examples = len(complete_scenarios)
    if claimed == RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT:
        run_status = (
            "passed"
            if measured == RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
            else "failed"
        )
    elif current is not None:
        run_status = "running"
    elif invalid or censored:
        run_status = "paused"
    elif claimed:
        run_status = "running"
    else:
        run_status = "waiting"
    if current is not None:
        location = (
            f"Trial {current.ordinal}/55 · {current.partition.value} "
            f"{current.kind.value} candidate {current.candidate_index + 1}"
        )
        current_event = (
            f"Current claim · trial {current.ordinal}/55 · {current.partition.value} "
            f"{current.kind.value} · candidate row {current.candidate_index + 1} · consumed"
        )
    elif next_unclaimed is not None:
        location = f"Next unclaimed trial {next_unclaimed.ordinal}/55 · exact plan loaded"
        current_event = (
            f"Next unclaimed · trial {next_unclaimed.ordinal}/55 · "
            f"{next_unclaimed.partition.value} {next_unclaimed.kind.value}"
        )
    else:
        location = "All 55 frozen trial identities terminal"
        current_event = "All frozen trial identities are claimed and terminal"
    if run_status == "passed":
        message = (
            "All 55 candidate trials are measured and all 14 question menus are complete. "
            "The model is still unfitted and has no live authority."
        )
        next_event = (
            "Next: fit once on 8 train examples, preserve 6 development examples untouched, "
            "then report against frozen baselines"
        )
    elif run_status in {"failed", "paused"}:
        message = (
            f"Campaign retained {invalid} invalid and {censored} censored one-shot trials. "
            "Consumed identities cannot retry; only untouched trials may continue."
        )
        next_event = (
            "Next: preserve every failure/censor terminal; continue only untouched identities "
            "under the exact frozen campaign"
        )
    elif run_status == "running":
        message = (
            f"Red outcome collection is active: {terminal_count}/55 terminals and "
            f"{complete_examples}/14 complete menus. No teacher or model is choosing actions."
        )
        next_event = (
            "Next: finish each candidate once; fit nothing until all usable train "
            "menus are complete"
        )
    else:
        message = (
            "The exact 14-question / 55-trial campaign is loaded with zero claimed trials. "
            "Controller execution still requires the separately named owner authorization."
        )
        next_event = (
            "Next: exact owner authorization for this frozen plan; no trial may retry after input"
        )
    dose = plan.dose
    return replace(
        base,
        run_status=run_status,
        stage="Completion-aware party learner · 55-trial outcome campaign",
        message=message,
        frame_count=frames,
        actions=controller_actions,
        stage_progress=terminal_count / RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
        location=location,
        model=replace(
            base.model,
            mode="waiting",
            candidate="Completion-aware party scorer v2 · outcomes not yet fitted",
            choice="No teacher/model decisions · deterministic safety policy only",
            decisions=0,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=replace(
            base.experiment,
            phase="training",
            zero_shot_completed=terminal_count,
            zero_shot_total=RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
            adaptation_completed=complete_examples,
            adaptation_total=14,
            sealed_completed=0,
            sealed_total=1,
            predictions_committed=False,
            heading="Party outcome collection",
            eyebrow="Red curriculum · one-shot cloned counterfactuals",
            counter_labels=(
                "Terminal candidate trials",
                "Complete question menus",
                "Authority promotions",
            ),
        ),
        events=(
            (
                f"Frozen campaign · source {plan.source_commit[:7]} · CI {plan.exact_ci_run} "
                f"attempt {plan.exact_ci_attempt} · plan {plan.plan_sha256[:8]}…"
            ),
            (
                f"Trial ledger · claims {claimed}/55 · terminals {terminal_count}/55 · "
                f"questions touched {len(question_claims)}/14"
            ),
            (
                f"Terminal status · measured {measured} · invalid {invalid} · censored {censored}"
            ),
            (
                f"Complete menus · train {train_complete}/8 · untouched development "
                f"{development_complete}/6 · total {complete_examples}/14"
            ),
            current_event,
            (
                f"Measured work · battles {battles} · encounter steps {encounter_steps} · "
                f"controller actions {controller_actions} · frames {frames}"
            ),
            (
                f"Recovery/switch cost · healing trips {healing_trips} · rotations {rotations}"
            ),
            (
                f"Per-trial dose · {dose.completed_battles} battles · steps "
                f"≤{dose.maximum_encounter_steps} "
                f"· actions ≤{dose.maximum_controller_actions} · frames ≤{dose.maximum_frames}"
            ),
            (
                f"Safety bounds · heals ≤{dose.maximum_healing_trips} · rotations "
                f"≤{dose.maximum_rotations} · faints {dose.maximum_faints}"
            ),
            "Clone rule · every candidate reloads the same frozen question start",
            "No retry · failure remains invalid · interrupted claim becomes censored",
            "Teacher 0 · predictions 0 · updates 0 · fits 0 · live authority zero",
            "Sealed Red 0 · Crystal 0 · full-game replays 0",
            (
                "Product target · transferable planning toward complete games and living "
                "Pokédexes, not memorized Red button paths"
            ),
            next_event,
        ),
    )


def _live_snapshot(
    base: DashboardSnapshot,
    *,
    partition: str,
    status: str,
    record: Mapping[str, object] | None,
    train_prepared: bool = False,
) -> DashboardSnapshot:
    label = partition.title()
    if status == "waiting":
        return base
    if status == "claimed":
        return replace(
            base,
            run_status="running",
            message=(
                f"{label} output identity is durably claimed. Waiting for the first "
                "path-free battle progress receipt."
            ),
            location=f"{label} natural PP preparation · starting",
            events=(
                f"{label} one-shot artifact claimed · no progress receipt yet",
                *base.events[:23],
            ),
        )
    if record is None:
        raise ProgressDashboardError("dashboard PP live record is missing")
    if status == "failed":
        return replace(
            base,
            run_status="failed",
            message=(
                f"{label} preparation stopped fail-closed. The private receipt retains the "
                "failure; this dashboard exposes no private path or game identity."
            ),
            location=f"{label} natural PP preparation · failed",
            events=(
                f"{label} preparation failed closed · no retry inferred by dashboard",
                *base.events[:23],
            ),
        )

    battles = _record_count(record, "battles_completed")
    encounter_steps = _record_count(record, "encounter_steps")
    actions = _record_count(record, "controller_actions")
    frames = _record_count(record, "frames_executed")
    protected_counts = tuple(
        _record_count(record, key)
        for key in (
            "candidate_menus_constructed",
            "learner_outcomes_opened",
            "teacher_queries",
            "model_predictions",
        )
    )
    if battles > 32 or encounter_steps > 10_000 or actions > 250_000 or frames > 5_000_000:
        raise ProgressDashboardError("dashboard PP progress exceeds its frozen bounds")
    if any(protected_counts):
        raise ProgressDashboardError("dashboard PP progress opened a prohibited context")
    current_pp = _record_count(
        record, "current_total_pp" if status == "running" else "final_total_pp"
    )
    maximum_pp = _record_count(record, "maximum_total_pp")
    if maximum_pp == 0 or current_pp > maximum_pp:
        raise ProgressDashboardError("dashboard PP total is invalid")
    if status == "passed":
        if (
            record.get("partition") != partition
            or record.get("final_pp_bin") != "middle"
            or any(
                _record_count(record, key)
                for key in (
                    "faints",
                    "new_persistent_statuses",
                    "heals",
                    "party_switches",
                    "captures",
                    "storage_accesses",
                    "model_updates",
                )
            )
        ):
            raise ProgressDashboardError("dashboard PP terminal state is inconsistent")
        retained_events = tuple(
            event
            for event in base.events
            if not event.startswith("Natural middle-PP preparations")
            and not event.startswith("Next:")
        )
        if partition == "train":
            preparation_event = (
                "Natural middle-PP preparations 1/2 · train complete · "
                "development authorization absent"
            )
            next_event = (
                "Next: separately authorize development once; if accepted, re-inventory both "
                "states and freeze the 8+6 menus"
            )
        elif train_prepared:
            preparation_event = (
                "Natural middle-PP preparations 2/2 · train and development complete"
            )
            next_event = (
                "Next: re-inventory both accepted states and freeze the exact 8+6 menus before "
                "opening any outcome"
            )
        else:
            preparation_event = "Development middle-PP preparation complete · train not reconciled"
            next_event = (
                "Next: reconcile the train receipt before claiming 2/2 or freezing the 8+6 menus"
            )
        return replace(
            base,
            run_status="passed",
            stage_progress=1.0,
            actions=actions,
            frame_count=frames,
            message=(
                f"{label} natural middle-PP state completed: {battles} battles, "
                f"{current_pp}/{maximum_pp} total PP, zero learner outcomes."
            ),
            location=f"{label} natural PP preparation · complete",
            events=(
                f"{label} PP state complete · battles {battles} · steps {encounter_steps} · "
                f"actions {actions} · frames {frames}",
                preparation_event,
                *retained_events[:21],
                next_event,
            ),
        )
    if status != "running":
        raise ProgressDashboardError("dashboard PP live status is unsupported")
    return replace(
        base,
        run_status="running",
        stage_progress=min(battles / 32, 0.99),
        actions=actions,
        frame_count=frames,
        message=(
            f"{label} preparation is running: {battles}/32 battle cap, "
            f"{current_pp}/{maximum_pp} total PP, no teacher/model/outcome access."
        ),
        location=f"{label} natural PP preparation · battle {battles}/32",
        events=(
            f"{label} live progress · battles {battles} · steps {encounter_steps} · "
            f"actions {actions} · frames {frames}",
            *base.events[:23],
        ),
    )


def _development_gate_snapshot(
    base: DashboardSnapshot,
    train_terminal: Mapping[str, object],
) -> DashboardSnapshot:
    accepted_train = _live_snapshot(
        base,
        partition="train",
        status="passed",
        record=train_terminal,
    )
    return replace(
        accepted_train,
        run_status="waiting",
        stage_progress=0.5,
        actions=0,
        frame_count=0,
        message=(
            "Train's natural middle-PP state is accepted. Development passes read-only "
            "preflight and requires its own exact owner authorization."
        ),
        location="Natural PP preparation gate · development authorization pending",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    evidence = _load_evidence()
    v4_evidence = _load_v4_evidence()
    catalog_evidence = _load_catalog_evidence()
    catalog_audit_evidence = _load_catalog_audit_evidence()
    catalog_receipt = _mapping(catalog_evidence, "catalog")
    catalog_sha256 = _receipt_digest(catalog_receipt, "catalog_sha256")
    preparation_base = _current_snapshot(evidence, v4_evidence)
    monitor_root = _require_monitor_root(args.private_artifact_root)
    campaign_plan = _load_campaign_plan(
        args.campaign_plan,
        args.campaign_plan_file_sha256,
    )
    campaign_store = (
        open_private_root(monitor_root, repository_root=PROJECT_ROOT)
        if campaign_plan is not None and monitor_root is not None
        else None
    )
    completed_train = False
    train_live_record: tuple[str, dict[str, object] | None] | None = None
    base_snapshot = preparation_base
    if campaign_plan is None and monitor_root is not None:
        train_live_record = _live_artifact_record(monitor_root, "train")
        completed_train = train_live_record[0] == "passed"
        if args.partition == "development" and completed_train:
            if train_live_record[1] is None:  # pragma: no cover - live reader owns this invariant
                raise ProgressDashboardError("dashboard train terminal is missing")
            base_snapshot = _development_gate_snapshot(
                preparation_base,
                train_live_record[1],
            )
    initial_live_record: tuple[str, dict[str, object] | None] | None = None
    initial_snapshot = base_snapshot
    if campaign_plan is None and monitor_root is not None:
        initial_live_record = (
            train_live_record
            if args.partition == "train"
            else _live_artifact_record(monitor_root, args.partition)
        )
        if initial_live_record is None:  # pragma: no cover - branch above always assigns it
            raise AssertionError("dashboard live record disappeared")
        initial_snapshot = _live_snapshot(
            base_snapshot,
            partition=args.partition,
            status=initial_live_record[0],
            record=initial_live_record[1],
            train_prepared=completed_train,
        )
    audited_snapshot = _audited_catalog_snapshot(
        _catalog_snapshot(initial_snapshot, catalog_evidence),
        catalog_audit_evidence,
    )
    initial_snapshot = (
        _campaign_snapshot(audited_snapshot, campaign_plan, campaign_store)
        if campaign_plan is not None
        else audited_snapshot
    )
    state = DashboardState(initial_snapshot)
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon-party-development-v2-readiness-dashboard-v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "venue_priors": 2,
                    "reserved_roots": "8 train / 6 development",
                    "pp_materializations": "2/2",
                    "read_only_preflights": "2/2",
                    "independent_audit": "catalog_input_integrity_verified",
                    "collector": (
                        "exact_14_example_55_trial_plan_loaded"
                        if campaign_plan is not None
                        else "implementation_qualification_in_progress"
                    ),
                    "authorization_pending": (
                        "exact_frozen_campaign_plan"
                        if campaign_plan is not None
                        else "after_collector_ci_and_read_only_preflight"
                    ),
                    "maximum_completed_battles": 32,
                    "minimum_battle_headroom": 5,
                    "frozen_menus": 14,
                    "catalog_sha256": catalog_sha256,
                    "outcome_collection_progress": (
                        f"{initial_snapshot.experiment.adaptation_completed}/14"
                    ),
                    "model_fit": False,
                    "teacher_queries": 0,
                    "controller_actions": initial_snapshot.actions,
                    "sealed_red_cases_opened": 0,
                    "crystal_cases_opened": 0,
                    "authority_promoted": False,
                    "private_path_fields": 0,
                    "live_progress_monitor": (
                        campaign_plan is not None and campaign_store is not None
                    ),
                    "live_game_frame": False,
                },
                sort_keys=True,
            )
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        last_snapshot = initial_snapshot
        try:
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                if campaign_plan is not None and campaign_store is not None:
                    refreshed = _campaign_snapshot(
                        audited_snapshot,
                        campaign_plan,
                        campaign_store,
                    )
                    if refreshed != last_snapshot:
                        state.publish(refreshed)
                        last_snapshot = refreshed
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
