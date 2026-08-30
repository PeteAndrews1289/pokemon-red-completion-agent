from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-r1-six-card-throughput-result-v1-2026-08-30.json"
)
RESULT_SHA256 = "9c64160bb3a3f955a5f356acd393f5d4909a6d5c0cad4efb05f754268516cecb"


def _result() -> dict[str, object]:
    return json.loads(RESULT_PATH.read_text(encoding="ascii"))


def test_r1_throughput_result_binds_the_exact_six_card_denominator() -> None:
    payload = RESULT_PATH.read_bytes()
    result = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == RESULT_SHA256
    assert result["schema"] == (
        "pokemon.red.living-dex-r1-six-card-throughput-result.v1"
    )
    assert result["source"] == {
        "cartridge_sha256": (
            "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
        ),
        "exact_ci_attempt": 1,
        "exact_ci_run": 33322464644,
        "exact_main_commit": "72f57d0a0fc6d68000ab4cfd75b8e0f4dde450fc",
        "source_bundle_sha256": (
            "f6502562b0711e81efc67bafdd26e523b6782627ef376afb18d543011d6bdea8"
        ),
    }
    rows = result["rows"]
    assert isinstance(rows, list)
    assert [row["ordinal"] for row in rows] == list(range(2, 8))
    assert len(rows) == 6
    assert sum(row["root_claims"] for row in rows) == 6


def test_r1_throughput_result_retains_successes_and_setup_failures() -> None:
    result = _result()
    rows = result["rows"]
    batch = result["batch"]
    assert isinstance(rows, list)
    assert isinstance(batch, dict)

    recorded = [row for row in rows if row["causal_train_example_recorded"]]
    setup_terminals = [
        row for row in rows if not row["causal_train_example_recorded"]
    ]
    assert len(recorded) == batch["causal_train_examples_recorded"] == 4
    assert len(setup_terminals) == batch["setup_terminals_without_example"] == 2
    assert batch["attempts"] == batch["claim_pairs_consumed"] == 6
    assert sum(row["controller_actions"] for row in rows) == 12209
    assert sum(row["emulator_frames"] for row in rows) == 609272
    assert sum(row["provider_executions"] for row in rows) == 4
    assert math.isclose(batch["selected_arm_settled_yield"], 4 / 6)
    assert math.isclose(batch["examples_per_outer_wall_clock_hour"], 23.968481)


def test_r1_throughput_result_reports_the_complete_action_free_corpus_audit() -> None:
    corpus = _result()["corpus_audit"]
    assert isinstance(corpus, dict)

    assert corpus["authenticated_causal_train_examples"] == 12
    assert corpus["batch_authenticated_examples"] == 4
    assert corpus["train_examples"] == 12
    assert corpus["development_examples"] == 0
    assert corpus["distinct_causal_identities"] == 12
    assert corpus["distinct_decision_identities"] == 12
    assert corpus["distinct_lineages"] == 12
    assert corpus["maximum_lineage_multiplicity"] == 1
    assert corpus["candidate_feature_rows"] == 36
    assert corpus["supported_candidate_feature_rows"] == 36
    assert corpus["distinct_selected_feature_rows"] == 12
    assert corpus["selected_feature_rank"] == 10
    assert set(corpus["selected_option_kind_counts"]) == {
        "acquire",
        "develop",
        "evolve",
        "explore",
        "manage_storage",
        "resupply",
        "unlock_access",
    }
    assert corpus["successful_examples"] == 2
    assert corpus["unsuccessful_examples"] == 10
    assert corpus["batch_successful_examples"] == 0
    assert corpus["batch_unsuccessful_examples"] == 4
    assert corpus["significantly_variable_outcome_heads"] == [
        "verified_success"
    ]
    assert corpus["all_six_claim_pairs_consumed"] is True


def test_r1_throughput_result_grants_no_fit_gameplay_or_transfer_authority() -> None:
    result = _result()
    learning = result["learning_state"]
    unsupported = result["claim_boundary"]["unsupported"]

    assert learning == {
        "authentic_causal_train_examples_after": 12,
        "authentic_causal_train_examples_before": 8,
        "authority_promotions": 0,
        "integration_fits": 1,
        "powered_model_fits": 0,
        "transfer_results": 0,
    }
    assert "model_quality_or_generalization" in unsupported
    assert "powered_red_fit_readiness" in unsupported
    assert "learned_gameplay_authority" in unsupported
    assert "crystal_execution" in unsupported
    assert result["publication"]["status"] == "result_pending_publication"


def test_r1_throughput_result_is_path_and_identity_free() -> None:
    payload = RESULT_PATH.read_text(encoding="ascii")
    result = json.loads(payload)

    assert "/Users/" not in payload
    assert "/Volumes/" not in payload
    assert result["privacy"] == {
        "private_identity_fields_published": 0,
        "private_path_fields_published": 0,
        "selected_arm_identity_published": False,
        "selected_outcome_detail_published": False,
    }
    assert result["execution_history"] == {
        "authenticated_zero_effect_preflights": 1,
        "gameplay_invocations": 6,
        "local_runtime_closure_sha256": (
            "3dd2037389febcf59a9b45f1f9c705b54889eea0d2445c3a61a1f19600992c62"
        ),
        "selected_root_path_failures_before_private_byte_read": 1,
        "source_or_runtime_bootstrap_failures_before_private_access": 2,
        "zero_effect_failures_changed_the_attempt_denominator": False,
    }
