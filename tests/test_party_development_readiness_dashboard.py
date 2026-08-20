from __future__ import annotations

import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest
from test_party_development_outcome_campaign import _plan
from test_party_development_outcome_lineage import _publish_invalid, _successor
from test_party_development_outcome_results import _result

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialClaim,
)
from pokemon_red_completion.party_development_outcome_results import (
    build_party_development_trial_terminal,
)
from pokemon_red_completion.party_development_readiness_dashboard import (
    PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA,
    PARTY_DEVELOPMENT_READINESS_STATUS,
    party_development_readiness_dashboard_snapshot,
)
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.progress_dashboard import ProgressDashboardError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_party_development_readiness_dashboard.py")
)


def _evidence() -> dict[str, object]:
    return {
        "schema": PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA,
        "status": PARTY_DEVELOPMENT_READINESS_STATUS,
        "prior": {
            "bound": True,
            "v1_model_canonical_sha256": "a" * 64,
            "v2_initial_model_canonical_sha256": "b" * 64,
            "train_examples": 13_709,
            "validation_examples": 7_030,
            "validation_correct": 7_023,
            "shape_baseline_correct": 6_725,
            "independent_validation_lineages": 1,
            "outcome_updates": 0,
        },
        "checkpoint_inventory": {
            "checkpoint_count": 81,
            "partition_counts": {"development": 27, "train": 54},
            "unique_semantic_contexts": {"development": 16, "train": 31},
            "ready_multi_candidate_contexts": {"development": 24, "train": 48},
            "hp_bins": {
                "development": ["high", "low", "middle"],
                "train": ["high", "low", "middle"],
            },
            "pp_bins": {
                "development": ["low", "middle"],
                "train": ["low", "middle"],
            },
            "evolution_routes": {
                "development": ["level", "none"],
                "train": ["level", "none"],
            },
            "goal_hints": {
                "development": [
                    "balance",
                    "collection",
                    "evolution",
                    "role_coverage",
                ],
                "train": [
                    "balance",
                    "collection",
                    "evolution",
                    "role_coverage",
                ],
            },
        },
        "reservation": {
            "reserved_roots": {"development": 6, "train": 8},
            "direct_roots_preflighted": 12,
            "frozen_menus": 0,
        },
        "venue_priors": {
            "entries": 2,
            "frozen": True,
        },
        "pp_preparation": {
            "reserved_sources": {"development": 1, "train": 1},
            "materialized_sources": {"development": 0, "train": 0},
            "contract_qualified": True,
            "controller_authorization_granted": False,
            "ordinary_battle_consumption": True,
            "healing_allowed": False,
            "party_switching_allowed": False,
            "memory_edit_allowed": False,
            "teacher_or_model_allowed": False,
            "maximum_completed_battles_per_source": 27,
            "maximum_encounter_steps_per_source": 10_000,
            "maximum_controller_actions_per_source": 250_000,
            "maximum_frames_per_source": 5_000_000,
        },
        "first_fit_gate": {
            "minimum_train_outcomes": 8,
            "minimum_development_outcomes": 6,
            "collected_train_outcomes": 0,
            "collected_development_outcomes": 0,
            "prospective_catalog_frozen": False,
            "candidate_adapter_ready": True,
            "venue_prior_registry_frozen": True,
            "model_fit": False,
            "authority_promoted": False,
        },
        "protected_access": {
            "controller_actions": 0,
            "teacher_queries": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
        },
    }


def test_readiness_dashboard_reports_zero_outcome_training_honestly() -> None:
    document = party_development_readiness_dashboard_snapshot(_evidence()).public_dict()

    assert document["run_status"] == "waiting"
    assert document["stage_progress"] == 0.0
    assert document["actions"] == 0
    assert document["model"]["mode"] == "waiting"  # type: ignore[index]
    assert document["experiment"]["adaptation"] == {  # type: ignore[index]
        "completed": 0,
        "total": 14,
    }
    components = document["learning_components"]
    assert isinstance(components, list)
    assert components[0]["train_examples"] == 13_709
    assert components[1]["train_examples"] == 0
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False)
    assert "model fitting has not begun" in encoded
    assert "Compatible venue priors 2/2" in encoded
    assert "Natural middle-PP preparations 0/2" in encoded
    assert "concrete frozen Red menus 0" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    (
        ("protected_access", "controller_actions", 1, "protected execution"),
        ("first_fit_gate", "model_fit", True, "overstates"),
        ("first_fit_gate", "collected_train_outcomes", 1, "unfrozen"),
        ("prior", "outcome_updates", 1, "cannot contain outcome updates"),
        ("pp_preparation", "controller_authorization_granted", True, "inconsistent"),
    ),
)
def test_readiness_dashboard_rejects_training_overclaims(
    section: str, key: str, value: object, match: str
) -> None:
    evidence = deepcopy(_evidence())
    nested = evidence[section]
    assert isinstance(nested, dict)
    nested[key] = value

    with pytest.raises(ProgressDashboardError, match=match):
        party_development_readiness_dashboard_snapshot(evidence)


def test_readiness_dashboard_script_uses_a_separate_local_port() -> None:
    parser = SCRIPT["_parser"]()
    args = parser.parse_args(["--no-browser", "--duration-seconds", "1"])

    assert args.port == 8767
    assert args.no_browser is True
    assert args.duration_seconds == 1
    assert args.private_artifact_root is None
    assert args.partition == "train"
    assert args.campaign_plan is None
    assert args.campaign_plan_file_sha256 is None
    assert SCRIPT["EVIDENCE_PATH"].name == ("party-development-v2-readiness-2026-08-16.json")
    assert SCRIPT["V4_EVIDENCE_PATH"].name == (
        "red-party-development-pp-materialization-v4-preflight-2026-08-16.json"
    )
    assert SCRIPT["CATALOG_EVIDENCE_PATH"].name == (
        "red-party-development-frozen-input-catalog-v1-result-2026-08-16.json"
    )
    assert SCRIPT["CATALOG_AUDIT_EVIDENCE_PATH"].name == (
        "red-party-development-frozen-input-catalog-v1-audit-2026-08-16.json"
    )


def test_campaign_dashboard_loads_only_the_exact_external_plan(tmp_path: Path) -> None:
    plan = _plan()
    path = tmp_path / "campaign.json"
    payload = (
        json.dumps(
            plan.private_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    assert SCRIPT["_load_campaign_plan"](path, digest) == plan
    with pytest.raises(ProgressDashboardError, match="bytes are invalid"):
        SCRIPT["_load_campaign_plan"](path, "0" * 64)
    with pytest.raises(ProgressDashboardError, match="supplied together"):
        SCRIPT["_load_campaign_plan"](path, None)


def test_tracked_readiness_evidence_loads_into_honest_snapshot() -> None:
    evidence = SCRIPT["_load_evidence"]()
    document = party_development_readiness_dashboard_snapshot(evidence).public_dict()

    assert evidence["status"] == PARTY_DEVELOPMENT_READINESS_STATUS
    assert document["run_status"] == "waiting"
    assert document["actions"] == 0
    assert document["experiment"]["adaptation"] == {  # type: ignore[index]
        "completed": 0,
        "total": 14,
    }
    assert document["model"]["teacher_queries"] == 0  # type: ignore[index]
    encoded = json.dumps(document, sort_keys=True)
    assert "model fitting has not begun" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_current_dashboard_projects_the_verified_v4_authorization_gate() -> None:
    document = SCRIPT["_current_snapshot"](
        SCRIPT["_load_evidence"](),
        SCRIPT["_load_v4_evidence"](),
    ).public_dict()

    assert document["run_status"] == "waiting"
    assert document["actions"] == 0
    assert document["location"] == ("Natural PP preparation gate · train authorization pending")
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False)
    assert "Read-only preflights 2/2" in encoded
    assert "Claude APPROVE to ask" in encoded
    assert "battles 32 · minimum headroom 5" in encoded
    assert "exact owner authorization for train once" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_current_dashboard_rejects_a_false_v4_authorization_claim() -> None:
    v4_evidence = deepcopy(SCRIPT["_load_v4_evidence"]())
    authorization = v4_evidence["authorization"]
    assert isinstance(authorization, dict)
    authorization["granted"] = True

    with pytest.raises(ProgressDashboardError, match="inconsistent"):
        SCRIPT["_current_snapshot"](_evidence(), v4_evidence)


def test_current_dashboard_projects_the_frozen_catalog_review_gate() -> None:
    base = SCRIPT["_current_snapshot"](
        SCRIPT["_load_evidence"](),
        SCRIPT["_load_v4_evidence"](),
    )
    evidence = SCRIPT["_load_catalog_evidence"]()

    document = SCRIPT["_catalog_snapshot"](base, evidence).public_dict()

    assert document["run_status"] == "waiting"
    assert document["stage_progress"] == 1.0
    assert document["actions"] == 0
    assert document["frame_count"] == 0
    assert document["location"] == ("Frozen 8+6 catalog · independent input review pending")
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False)
    assert "14 questions · 8 train / 6 development" in encoded
    assert "Natural middle-PP preparations 2/2" in encoded
    assert "Answers 0/14" in encoded
    assert "separately authorize 8+6 outcomes" in encoded
    assert "model fitting has not begun" in encoded
    assert "frozen menus 0" not in encoded
    assert "concrete frozen Red menus 0" not in encoded
    assert "PP bins · train high" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_current_dashboard_rejects_a_catalog_count_overclaim() -> None:
    base = SCRIPT["_current_snapshot"](
        SCRIPT["_load_evidence"](),
        SCRIPT["_load_v4_evidence"](),
    )
    evidence = deepcopy(SCRIPT["_load_catalog_evidence"]())
    catalog = evidence["catalog"]
    assert isinstance(catalog, dict)
    catalog["question_count"] = 13

    with pytest.raises(ProgressDashboardError, match="inconsistent"):
        SCRIPT["_catalog_snapshot"](base, evidence)


def test_current_dashboard_projects_the_verified_input_outcome_gate() -> None:
    base = SCRIPT["_catalog_snapshot"](
        SCRIPT["_current_snapshot"](
            SCRIPT["_load_evidence"](),
            SCRIPT["_load_v4_evidence"](),
        ),
        SCRIPT["_load_catalog_evidence"](),
    )

    document = SCRIPT["_audited_catalog_snapshot"](
        base,
        SCRIPT["_load_catalog_audit_evidence"](),
    ).public_dict()

    assert document["run_status"] == "waiting"
    assert document["stage_progress"] == 1.0
    assert document["actions"] == 0
    assert document["frame_count"] == 0
    assert document["location"] == ("Verified 8+6 inputs · 55-trial collector build")
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False)
    assert "All fourteen frozen Red questions independently reconstruct" in encoded
    assert "55 candidate rows · 66 features · 49 varying · 12 distinct menus" in encoded
    assert "19/19 boundary probes rejected · 2/2 re-hashed forgeries rejected" in encoded
    assert "build, attack, publish and read-only preflight the 55-trial collector" in encoded
    assert "trials 0/55" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_current_dashboard_rejects_a_false_catalog_audit_claim() -> None:
    evidence = deepcopy(SCRIPT["_load_catalog_audit_evidence"]())
    protected = evidence["protected_access"]
    assert isinstance(protected, dict)
    protected["outcomes_opened"] = 1

    with pytest.raises(ProgressDashboardError, match="inconsistent"):
        SCRIPT["_audited_catalog_snapshot"](
            SCRIPT["_current_snapshot"](
                SCRIPT["_load_evidence"](),
                SCRIPT["_load_v4_evidence"](),
            ),
            evidence,
        )


def _campaign_dashboard_base():
    return SCRIPT["_audited_catalog_snapshot"](
        SCRIPT["_catalog_snapshot"](
            SCRIPT["_current_snapshot"](
                SCRIPT["_load_evidence"](),
                SCRIPT["_load_v4_evidence"](),
            ),
            SCRIPT["_load_catalog_evidence"](),
        ),
        SCRIPT["_load_catalog_audit_evidence"](),
    )


def _campaign_store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()
    return initialize_private_root(
        private,
        repository_root=repository,
        allow_same_device=True,
        git_worktree_probe=lambda _path: False,
    )


def test_campaign_dashboard_tracks_the_one_shot_trial_ledger(tmp_path: Path) -> None:
    plan = _plan()
    store = _campaign_store(tmp_path)
    base = _campaign_dashboard_base()

    waiting = SCRIPT["_campaign_snapshot"](base, plan, store).public_dict()
    assert waiting["run_status"] == "waiting"
    assert waiting["experiment"]["zero_shot"] == {  # type: ignore[index]
        "completed": 0,
        "total": 55,
    }
    assert waiting["experiment"]["adaptation"] == {  # type: ignore[index]
        "completed": 0,
        "total": 14,
    }

    first_assignment = plan.assignments[0]
    first_claim = PartyDevelopmentOutcomeTrialClaim.build(plan, first_assignment)
    store.publish_sealed_record(
        f"{first_assignment.trial_id}-claim",
        kind=SCRIPT["_CAMPAIGN_CLAIM_KIND"],
        record=first_claim.private_dict(),
    )
    running = SCRIPT["_campaign_snapshot"](base, plan, store).public_dict()
    assert running["run_status"] == "running"
    assert "Trial 1/55" in running["location"]
    assert "consumed" in json.dumps(running, ensure_ascii=False)

    for ordinal in range(1, 7):
        assignment = plan.assignments[ordinal - 1]
        result, evidence = _result(ordinal)
        claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
        if ordinal > 1:
            store.publish_sealed_record(
                f"{assignment.trial_id}-claim",
                kind=SCRIPT["_CAMPAIGN_CLAIM_KIND"],
                record=claim.private_dict(),
            )
        store.publish_sealed_record(
            f"{assignment.trial_id}-terminal",
            kind=SCRIPT["_CAMPAIGN_TERMINAL_KIND"],
            record=build_party_development_trial_terminal(
                result,
                evidence=evidence,
            ),
        )

    progressed = SCRIPT["_campaign_snapshot"](base, plan, store).public_dict()
    assert progressed["run_status"] == "running"
    assert progressed["stage_progress"] == 6 / 55
    assert progressed["actions"] == 2_400
    assert progressed["frame_count"] == 240_000
    assert progressed["experiment"]["zero_shot"] == {  # type: ignore[index]
        "completed": 6,
        "total": 55,
    }
    assert progressed["experiment"]["adaptation"] == {  # type: ignore[index]
        "completed": 1,
        "total": 14,
    }
    encoded = json.dumps(progressed, sort_keys=True, ensure_ascii=False)
    assert "measured 6 · invalid 0 · censored 0" in encoded
    assert "Teacher 0 · predictions 0 · updates 0 · fits 0" in encoded
    assert "No retry" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_campaign_dashboard_projects_successor_tombstone_without_retry(
    tmp_path: Path,
) -> None:
    predecessor = _plan()
    store = _campaign_store(tmp_path)
    _publish_invalid(store, predecessor, predecessor.assignments[0])
    successor = _successor(predecessor, store)

    snapshot = SCRIPT["_campaign_snapshot"](
        _campaign_dashboard_base(),
        successor,
        store,
    ).public_dict()

    assert snapshot["run_status"] == "waiting"
    assert "Next unclaimed trial 2/55" in snapshot["location"]
    assert snapshot["stage_progress"] == 1 / 55
    assert snapshot["experiment"]["zero_shot"] == {  # type: ignore[index]
        "completed": 1,
        "total": 55,
    }
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    assert "preserves 1 consumed trial" in encoded
    assert "54 untouched identities" in encoded
    assert "invalid 1" in encoded


def test_live_dashboard_projects_path_free_progress_and_terminal() -> None:
    base = SCRIPT["_current_snapshot"](
        SCRIPT["_load_evidence"](),
        SCRIPT["_load_v4_evidence"](),
    )
    progress = {
        "record_type": "party_development_pp_materialization_progress",
        "schema_version": 1,
        "battles_completed": 4,
        "encounter_steps": 18,
        "current_total_pp": 71,
        "maximum_total_pp": 80,
        "controller_actions": 240,
        "frames_executed": 12_000,
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
    }

    running = SCRIPT["_live_snapshot"](
        base,
        partition="train",
        status="running",
        record=progress,
    ).public_dict()
    assert running["run_status"] == "running"
    assert running["stage_progress"] == 4 / 32
    assert running["actions"] == 240
    assert running["frame_count"] == 12_000
    assert "71/80 total PP" in running["message"]

    terminal = {
        **progress,
        "record_type": "party_development_pp_materialization_terminal",
        "final_total_pp": 52,
        "battles_completed": 11,
        "partition": "train",
        "final_pp_bin": "middle",
        "faints": 0,
        "new_persistent_statuses": 0,
        "heals": 0,
        "party_switches": 0,
        "captures": 0,
        "storage_accesses": 0,
        "model_updates": 0,
    }
    terminal.pop("current_total_pp")
    passed = SCRIPT["_live_snapshot"](
        base,
        partition="train",
        status="passed",
        record=terminal,
    ).public_dict()
    assert passed["run_status"] == "passed"
    assert passed["stage_progress"] == 1.0
    assert "zero learner outcomes" in passed["message"]
    encoded = json.dumps(passed, sort_keys=True, ensure_ascii=False)
    assert "Natural middle-PP preparations 1/2" in encoded
    assert "development authorization absent" in encoded
    assert "separately authorize development once" in encoded
    assert "Natural middle-PP preparations 0/2" not in encoded
    assert "exact owner authorization for train once" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    development_gate = SCRIPT["_development_gate_snapshot"](base, terminal).public_dict()
    assert development_gate["run_status"] == "waiting"
    assert development_gate["stage_progress"] == 0.5
    assert development_gate["actions"] == 0
    assert development_gate["frame_count"] == 0
    assert development_gate["location"] == (
        "Natural PP preparation gate · development authorization pending"
    )
    development_gate_text = json.dumps(
        development_gate,
        sort_keys=True,
        ensure_ascii=False,
    )
    assert "Train's natural middle-PP state is accepted" in development_gate_text
    assert "Natural middle-PP preparations 1/2" in development_gate_text

    development_terminal = {**terminal, "partition": "development"}
    completed = SCRIPT["_live_snapshot"](
        SCRIPT["_development_gate_snapshot"](base, terminal),
        partition="development",
        status="passed",
        record=development_terminal,
        train_prepared=True,
    ).public_dict()
    completed_text = json.dumps(completed, sort_keys=True, ensure_ascii=False)
    assert "Natural middle-PP preparations 2/2" in completed_text
    assert "freeze the exact 8+6 menus" in completed_text


def test_live_dashboard_reads_only_complete_path_free_records(tmp_path: Path) -> None:
    (tmp_path / ".pokemon-red-completion-private-root.json").write_text(
        '{"format":"pokemon-red-completion-private-root","schema_version":1}\n',
        encoding="ascii",
    )
    artifact = tmp_path / "red-party-pp-materialization-v1-train.partial"
    artifact.mkdir()
    progress = {
        "record_type": "party_development_pp_materialization_progress",
        "schema_version": 1,
        "battles_completed": 1,
        "encounter_steps": 3,
        "current_total_pp": 78,
        "maximum_total_pp": 80,
        "controller_actions": 40,
        "frames_executed": 2_000,
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
    }
    (artifact / "progress.jsonl").write_text(
        json.dumps(progress, sort_keys=True) + "\n",
        encoding="ascii",
    )

    root = SCRIPT["_require_monitor_root"](tmp_path)
    assert root == tmp_path
    status, record = SCRIPT["_live_artifact_record"](root, "train")
    assert status == "running"
    assert record == progress


def test_live_dashboard_rejects_progress_beyond_the_frozen_cap() -> None:
    base = SCRIPT["_current_snapshot"](
        SCRIPT["_load_evidence"](),
        SCRIPT["_load_v4_evidence"](),
    )
    progress = {
        "record_type": "party_development_pp_materialization_progress",
        "schema_version": 1,
        "battles_completed": 33,
        "encounter_steps": 0,
        "current_total_pp": 50,
        "maximum_total_pp": 80,
        "controller_actions": 0,
        "frames_executed": 0,
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
    }

    with pytest.raises(ProgressDashboardError, match="exceeds"):
        SCRIPT["_live_snapshot"](
            base,
            partition="train",
            status="running",
            record=progress,
        )

    progress["battles_completed"] = 1
    progress["learner_outcomes_opened"] = 1
    with pytest.raises(ProgressDashboardError, match="prohibited"):
        SCRIPT["_live_snapshot"](
            base,
            partition="train",
            status="running",
            record=progress,
        )
