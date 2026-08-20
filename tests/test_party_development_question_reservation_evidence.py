from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.party_development_question_reservations import (
    PARTY_DEVELOPMENT_QUESTION_RESERVATION_SUMMARY_SCHEMA,
    PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "party-development-question-reservation-2026-08-15.json"
)


def test_public_question_reservation_records_the_exact_closed_boundary() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["schema"] == PARTY_DEVELOPMENT_QUESTION_RESERVATION_SUMMARY_SCHEMA
    assert evidence["reservation_count"] == 14
    assert evidence["partition_counts"] == {"development": 6, "train": 8}
    assert evidence["choice_kind_partition_counts"] == {
        "development:trainee": 3,
        "development:venue": 3,
        "train:trainee": 4,
        "train:venue": 4,
    }
    assert evidence["source_pp_bins"] == {
        "development": ["high"],
        "train": ["high"],
    }
    assert evidence["prospective_pp_bins_after_materialization"] == {
        "development": ["high", "middle"],
        "train": ["high", "middle"],
    }
    assert evidence["qualified_venue_priors"] == 1
    assert evidence["minimum_venue_priors_for_genuine_venue_menu"] == 2
    assert evidence["pp_materialization_protocol_sha256"] == (
        PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256
    )
    assert evidence["catalog_freeze_ready"] is False
    assert evidence["candidate_menus_frozen"] == 0
    assert evidence["outcomes_opened"] == 0
    assert evidence["model_updates"] == 0
    assert evidence["controller_actions"] == 0
    assert evidence["teacher_queries"] == 0
    assert evidence["sealed_test_cases_opened"] == 0
    assert evidence["crystal_cases_opened"] == 0
    assert evidence["authority_promoted"] is False


def test_public_question_reservation_has_no_private_identity_or_path() -> None:
    encoded = EVIDENCE_PATH.read_text(encoding="utf-8")

    assert '"source_checkpoint_id"' not in encoded
    assert '"source_state_sha256"' not in encoded
    assert '"features":' not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
