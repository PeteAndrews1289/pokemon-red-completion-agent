from __future__ import annotations

import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.party_development_readiness_dashboard import (
    PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA,
    PARTY_DEVELOPMENT_READINESS_STATUS,
    party_development_readiness_dashboard_snapshot,
)
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
        "first_fit_gate": {
            "minimum_train_outcomes": 8,
            "minimum_development_outcomes": 6,
            "collected_train_outcomes": 0,
            "collected_development_outcomes": 0,
            "prospective_catalog_frozen": False,
            "candidate_adapter_ready": False,
            "venue_prior_registry_frozen": False,
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
    encoded = json.dumps(document, sort_keys=True)
    assert "model fitting has not begun" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    (
        ("protected_access", "controller_actions", 1, "protected execution"),
        ("first_fit_gate", "model_fit", True, "overstates"),
        ("first_fit_gate", "collected_train_outcomes", 1, "unfrozen"),
        ("prior", "outcome_updates", 1, "cannot contain outcome updates"),
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

    assert args.port == 8766
    assert args.no_browser is True
    assert args.duration_seconds == 1
