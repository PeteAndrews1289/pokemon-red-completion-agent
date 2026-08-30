from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-r1-successor-completion-result-v1-2026-08-30.json"
)
RESULT_SHA256 = "d00f64c5994ac4c327c3a004cbf902a08ecfd1f522ba7745aee71657295f28dd"


def _result() -> dict[str, object]:
    return json.loads(RESULT_PATH.read_text(encoding="ascii"))


def test_r1_successor_completion_binds_exact_source_and_final_denominator() -> None:
    payload = RESULT_PATH.read_bytes()
    result = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == RESULT_SHA256
    assert result["schema"] == (
        "pokemon.red.living-dex-r1-successor-completion-result.v1"
    )
    assert result["source"] == {
        "cartridge_sha256": (
            "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
        ),
        "exact_ci_attempt": 1,
        "exact_ci_run": 33329384186,
        "exact_main_commit": "a358014fb2dfe4193c9474ee1cc008cd249eb03c",
        "source_bundle_sha256": (
            "f6502562b0711e81efc67bafdd26e523b6782627ef376afb18d543011d6bdea8"
        ),
    }
    rows = result["rows"]
    assert isinstance(rows, list)
    assert [row["ordinal"] for row in rows] == list(range(8, 16))
    assert len(rows) == 8
    assert sum(row["root_claims"] for row in rows) == 8


def test_r1_successor_completion_retains_settled_and_setup_only_terminals() -> None:
    result = _result()
    rows = result["rows"]
    batch = result["batch"]
    complete = result["complete_successor"]
    assert isinstance(rows, list)
    assert isinstance(batch, dict)
    assert isinstance(complete, dict)

    recorded = [row for row in rows if row["causal_train_example_recorded"]]
    setup_only = [row for row in rows if not row["causal_train_example_recorded"]]
    assert len(recorded) == batch["causal_train_examples_recorded"] == 6
    assert len(setup_only) == batch["setup_terminals_without_example"] == 2
    assert batch["attempts"] == batch["claim_pairs_consumed"] == 8
    assert sum(row["controller_actions"] for row in rows) == 9658
    assert sum(row["emulator_frames"] for row in rows) == 488081
    assert sum(row["provider_executions"] for row in rows) == 6
    assert math.isclose(batch["selected_arm_settled_yield"], 6 / 8)
    assert math.isclose(batch["examples_per_outer_wall_clock_hour"], 41.300191)
    assert complete == {
        "attempts": 16,
        "causal_train_examples_recorded": 12,
        "claim_pairs_consumed": 16,
        "controller_actions": 30367,
        "emulator_frames": 1500787,
        "selected_arm_settled_yield": 0.75,
        "setup_terminals_without_example": 4,
    }


def test_r1_successor_completion_reports_action_free_corpus_information() -> None:
    corpus = _result()["corpus_audit"]
    assert isinstance(corpus, dict)

    assert corpus["authenticated_causal_train_examples"] == 18
    assert corpus["batch_authenticated_examples"] == 6
    assert corpus["train_examples"] == 18
    assert corpus["development_examples"] == 0
    assert corpus["distinct_causal_identities"] == 18
    assert corpus["distinct_decision_identities"] == 18
    assert corpus["distinct_lineages"] == 18
    assert corpus["maximum_lineage_multiplicity"] == 1
    assert corpus["candidate_feature_rows"] == 54
    assert corpus["supported_candidate_feature_rows"] == 54
    assert corpus["distinct_selected_feature_rows"] == 18
    assert corpus["selected_feature_rank"] == 11
    assert set(corpus["selected_option_kind_counts"]) == {
        "acquire",
        "develop",
        "evolve",
        "explore",
        "manage_storage",
        "resupply",
        "unlock_access",
    }
    assert corpus["successful_examples"] == 3
    assert corpus["unsuccessful_examples"] == 15
    assert corpus["batch_successful_examples"] == 1
    assert corpus["batch_unsuccessful_examples"] == 5
    assert corpus["significantly_variable_outcome_heads"] == ["verified_success"]
    assert corpus["all_sixteen_successor_claim_pairs_consumed"] is True


def test_r1_successor_completion_grants_no_fit_gameplay_or_transfer_authority() -> None:
    result = _result()
    learning = result["learning_state"]
    unsupported = result["claim_boundary"]["unsupported"]

    assert learning == {
        "authentic_causal_train_examples_after": 18,
        "authentic_causal_train_examples_before": 12,
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


def test_r1_successor_completion_is_path_identity_and_prediction_free() -> None:
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
        "gameplay_invocations": 8,
        "local_runtime_closure_sha256": (
            "3dd2037389febcf59a9b45f1f9c705b54889eea0d2445c3a61a1f19600992c62"
        ),
        "owner_only_staged_files": 16,
        "preflight_bootstrap_locale_failures_before_source_authentication": 1,
        "preflight_production_process_invocations_total": 2,
        "runtime_diagnostics_with_relative_path_corrected_before_production": 1,
        "zero_effect_failures_changed_the_attempt_denominator": False,
    }
    assert set(result["claim_boundary"]["unsupported"]) >= {
        "model_quality_or_generalization",
        "learned_gameplay_authority",
        "sealed_red_evaluation",
        "crystal_execution",
        "cross_title_transfer",
        "living_pokedex_completion",
    }
