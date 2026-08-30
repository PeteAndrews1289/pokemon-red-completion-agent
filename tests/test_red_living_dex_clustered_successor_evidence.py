from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pokemon_red_completion.red_living_dex_clustered_successor import (
    RedLivingDexClusteredSuccessorDesign,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN,
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_RUNNER_SHA256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MACHINE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-successor-capacity-machine-result-v1-2026-08-29.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-successor-capacity-v1-2026-08-29.json"
)
QUALIFICATION_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-freezer-local-qualification-v1-2026-08-29.json"
)
FREEZE_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-freeze-result-v1-2026-08-29.json"
)
CONSUMER_QUALIFICATION_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-train-consumer-local-qualification-v1-2026-08-29.json"
)
PREFLIGHT_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-train-preflight-result-v1-2026-08-29.json"
)
ORDINAL_ZERO_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-train-ordinal-0-result-v1-2026-08-30.json"
)
ORDINAL_ONE_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-successor-train-ordinal-1-result-v1-2026-08-30.json"
)
INTEGRATION_READINESS_MACHINE_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-causal-integration-readiness-machine-result-v1-2026-08-30.json"
)
INTEGRATION_READINESS_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-causal-integration-readiness-result-v1-2026-08-30.json"
)
INTEGRATION_FIT_FAILURE_MACHINE_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-causal-integration-fit-machine-failure-v1-2026-08-30.json"
)
INTEGRATION_FIT_MACHINE_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-causal-integration-fit-machine-result-v1-2026-08-30.json"
)
INTEGRATION_FIT_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-causal-integration-fit-result-v1-2026-08-30.json"
)
MACHINE_SHA256 = "871c1d5ca12592b4ede506b877b04b8175c61bddb9338fcf5a683d8a0512fbf2"
RESULT_SHA256 = "db8a5b3805bc6811b3e4266f80506f3cd4f2502aa7ddef32226b02489340b5f4"
QUALIFICATION_SHA256 = (
    "492fd428914b36c30f79cd19bf7ab3cffede7bacee1fcffd3979b5bd08c0eca9"
)
FREEZE_RESULT_SHA256 = (
    "a58e6a2dfa2741a340cc23e4cab098ff952c620421f8fa835a5412bc09102925"
)
CONSUMER_QUALIFICATION_SHA256 = (
    "99b998575b660ba12078e5979c15cb8e8e920845bb1c9ca3b682a77a44543777"
)
PREFLIGHT_RESULT_SHA256 = (
    "f7e5d8de7651b5e53ad51166daac28bc6c8c72eecf449026cfb268ceb52caac5"
)
ORDINAL_ZERO_RESULT_SHA256 = (
    "be53cadccce21482a7831617d0623575161cf27295cea2a9b7dbaaf42986ef4d"
)
ORDINAL_ONE_RESULT_SHA256 = (
    "283113a41822a5cb03f974c0ec2a04fd3d7aa36c2c57e44c4ef08eb7ba30c7ec"
)
INTEGRATION_READINESS_MACHINE_SHA256 = (
    "0a6ad9c6d051b345223d4e230b269c288befdfefc0ef843c8d2ba03f068d7ee8"
)
INTEGRATION_READINESS_RESULT_SHA256 = (
    "d0fcaeb7bde027d4320d2c6b4a119b98a0bf84f2d4a4d56f2104bd24f76f5bff"
)
INTEGRATION_FIT_FAILURE_MACHINE_SHA256 = (
    "d2e996af46dc426a6e4bc120c83559a878f3d97b1849d4dcde998b0facf63415"
)
INTEGRATION_FIT_MACHINE_SHA256 = (
    "16d5f26c55634878eb054924c132dca5de9d0f842d5f404a130aa823c0df91f4"
)
INTEGRATION_FIT_RESULT_SHA256 = (
    "7b5eef3c79f8475721534d8214670546dadf97e86b2ff9f4e682332e312abfe4"
)


def test_successor_capacity_evidence_matches_the_exact_action_free_census() -> None:
    machine_payload = MACHINE_PATH.read_bytes()
    result_payload = RESULT_PATH.read_bytes()
    machine = json.loads(machine_payload)
    result = json.loads(result_payload)

    assert hashlib.sha256(machine_payload).hexdigest() == MACHINE_SHA256
    assert hashlib.sha256(result_payload).hexdigest() == RESULT_SHA256
    assert result["source"]["machine_result_sha256"] == MACHINE_SHA256
    assert machine["status"] == (
        "authenticated_action_free_clustered_inventory_censused"
    )
    assert machine["authenticated_contexts"] == 81
    assert machine["consumed_contexts"] == 13
    assert machine["eligible_root_pool"] == 59
    assert machine["source_train_roots"] == 36
    assert machine["source_validation_roots"] == 23
    assert machine["roots_with_any_compatible_template"] == 55
    assert machine["clustered_integration"]["train_lineages"] == 8
    assert machine["clustered_integration"]["development_lineages"] == 4
    assert len(machine["clustered_integration"]["train_option_kinds"]) == 7
    assert len(machine["clustered_integration"]["development_option_kinds"]) == 7
    assert machine["clustered_integration"]["lineage_overlap"] == 0


def test_successor_capacity_result_freezes_design_without_claiming_a_schedule() -> None:
    result = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    design = RedLivingDexClusteredSuccessorDesign()

    assert result["status"] == (
        "action_free_successor_capacity_passed_private_freeze_pending"
    )
    assert result["successor_design"] == {
        **design.public_dict(),
        "design_sha256": design.design_sha256,
    }
    assert result["capacity_gate"]["gate_passed"] is True
    assert result["capacity_gate"]["fixed_successor_schedule_materialized"] is False
    assert result["capacity_gate"]["stronger_policy_capacity_falsifier_pending"] is True
    assert "sixteen_train_schedule_materialized" in result["claim_boundary"][
        "unsupported"
    ]
    assert result["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in result["protected_effects"].items()
        if key != "collection_authorized"
    )


def test_successor_capacity_public_artifacts_disclose_no_private_fields() -> None:
    for path in (MACHINE_PATH, RESULT_PATH):
        payload = path.read_text(encoding="ascii")
        assert '"private_identity_fields":0' in payload or (
            '"private_identity_fields"' not in payload
        )
        assert '"private_path_fields":0' in payload or (
            '"private_path_fields"' not in payload
        )
        assert "/Users/" not in payload
        assert "/Volumes/" not in payload


def test_successor_local_qualification_binds_the_exact_implementation() -> None:
    payload = QUALIFICATION_PATH.read_bytes()
    receipt = json.loads(payload)
    design = RedLivingDexClusteredSuccessorDesign()

    assert hashlib.sha256(payload).hexdigest() == QUALIFICATION_SHA256
    assert receipt["status"] == (
        "locally_qualified_publication_and_exact_ci_pending"
    )
    assert receipt["implementation"]["capacity_receipt_sha256"] == RESULT_SHA256
    assert receipt["implementation"]["successor_design"]["design_sha256"] == (
        design.design_sha256
    )
    assert receipt["implementation"]["successor_design"]["policy_sha256"] == (
        design.policy.policy_sha256
    )
    freeze_result = json.loads(FREEZE_RESULT_PATH.read_text(encoding="ascii"))
    assert freeze_result["publication"]["source_commit"] == (
        "d4da25be4c412946ee4d26d138249232219da6a1"
    )
    expected_component_hashes = {
        "action_free_freezer": (
            "13e47acda4e160f2931263cb927b0747384da2893398408fa57e60dacaa0c1ff"
        ),
        "private_plan_contract": (
            "bf4fbfa6544d0360d51fe7129a9bfc89eae48c47a7f9a1b2027eb14342788ae2"
        ),
        "setup_admission": (
            "4a61e33d0fd196cb18eeebf8cba477e8693d57b0f37f0c06be676a0c9e695cbf"
        ),
        "train_only_consumer": (
            "b37faccfa79de2a0f04991410aa968a42d07fadc2f4d03895f45748cfdc8c54e"
        ),
    }
    for component, expected_sha256 in expected_component_hashes.items():
        assert receipt["implementation"][component]["sha256"] == expected_sha256
    for component in (
        "action_free_freezer",
        "private_plan_contract",
        "setup_admission",
    ):
        binding = receipt["implementation"][component]
        assert hashlib.sha256(
            (PROJECT_ROOT / binding["path"]).read_bytes()
        ).hexdigest() == binding["sha256"]
    design_binding = receipt["implementation"]["successor_design"]
    assert hashlib.sha256(
        (PROJECT_ROOT / design_binding["path"]).read_bytes()
    ).hexdigest() == design_binding["sha256"]


def test_successor_local_qualification_preserves_the_zero_effect_boundary() -> None:
    receipt = json.loads(QUALIFICATION_PATH.read_text(encoding="ascii"))
    contract = receipt["plan_and_consumer_contract"]

    assert contract["train_scenarios"] == 16
    assert contract["development_scenarios"] == 4
    assert contract["distinct_lineages"] == 20
    assert contract["train_ordinals_addressable"] == list(range(16))
    assert contract["development_outcome_access"] is False
    assert contract["exact_private_plan_binding_exists"] is False
    assert receipt["publication"] == {
        "exact_candidate_commit": None,
        "exact_candidate_ci": None,
        "status": "pending",
    }
    assert "private_successor_plan_frozen" in receipt["claim_boundary"][
        "unsupported"
    ]
    assert receipt["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in receipt["protected_effects"].items()
        if key != "collection_authorized"
    )


def test_successor_local_qualification_is_path_free() -> None:
    payload = QUALIFICATION_PATH.read_text(encoding="ascii")

    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_successor_freeze_result_binds_the_exact_inert_private_plan() -> None:
    payload = FREEZE_RESULT_PATH.read_bytes()
    result = json.loads(payload)
    frozen = FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN

    assert hashlib.sha256(payload).hexdigest() == FREEZE_RESULT_SHA256
    assert result["status"] == (
        "private_clustered_successor_schedule_frozen_and_independently_"
        "validated_exact_consumer_binding_next"
    )
    assert result["freeze"]["private_plan_sha256"] == (
        frozen.private_plan_sha256
    )
    assert result["freeze"]["plan_manifest_sha256"] == (
        frozen.plan_manifest_sha256
    )
    assert result["freeze"]["plan_record_sha256"] == (
        frozen.plan_record_sha256
    )
    assert result["freeze"]["schedule_sha256"] == frozen.schedule_sha256
    assert result["freeze"]["policy_sha256"] == frozen.policy_sha256
    assert result["freeze"]["train_scenarios"] == frozen.train_scenarios
    assert result["freeze"]["development_scenarios"] == (
        frozen.development_scenarios
    )
    assert result["freeze"]["lineage_overlap"] == 0
    assert result["independent_validation"]["private_plan_reopened"] is True
    assert result["source_bindings"]["local_qualification_sha256"] == (
        QUALIFICATION_SHA256
    )


def test_successor_freeze_result_reports_no_learning_or_private_leakage() -> None:
    payload = FREEZE_RESULT_PATH.read_text(encoding="ascii")
    result = json.loads(payload)

    assert result["interpretation"]["authentic_causal_train_examples_before"] == 6
    assert result["interpretation"]["authentic_causal_train_examples_after"] == 6
    assert result["interpretation"]["integration_fit_allowed_now"] is False
    assert result["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in result["protected_effects"].items()
        if key != "collection_authorized"
    )
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_successor_consumer_qualification_binds_current_source_and_plan() -> None:
    payload = CONSUMER_QUALIFICATION_PATH.read_bytes()
    receipt = json.loads(payload)
    frozen = FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN

    assert hashlib.sha256(payload).hexdigest() == CONSUMER_QUALIFICATION_SHA256
    assert receipt["status"] == (
        "locally_qualified_exact_source_publication_pending"
    )
    assert receipt["exact_plan_binding"] == {
        "causal_runner_sha256": RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_RUNNER_SHA256,
        "freeze_result_sha256": FREEZE_RESULT_SHA256,
        "plan_manifest_sha256": frozen.plan_manifest_sha256,
        "plan_record_sha256": frozen.plan_record_sha256,
        "policy_sha256": frozen.policy_sha256,
        "private_plan_sha256": frozen.private_plan_sha256,
        "record_id": frozen.record_id,
        "record_kind": frozen.record_kind,
        "schedule_sha256": frozen.schedule_sha256,
    }
    for component in (
        "execution_cli",
        "independent_validator",
        "train_only_consumer",
    ):
        binding = receipt["implementation"][component]
        assert hashlib.sha256(
            (PROJECT_ROOT / binding["path"]).read_bytes()
        ).hexdigest() == binding["sha256"]
    assert receipt["local_gate"]["focused_successor_boundary_suite"] == {
        "passed": 73,
        "seconds": 154.89,
    }
    assert receipt["local_gate"]["full_repository_suite"]["passed"] == 5787


def test_successor_consumer_qualification_reports_zero_effects_and_no_leakage() -> None:
    payload = CONSUMER_QUALIFICATION_PATH.read_text(encoding="ascii")
    receipt = json.loads(payload)
    contract = receipt["consumer_contract"]

    assert contract["real_plan_train_rows_reopened"] == 16
    assert contract["real_plan_distinct_train_lineages_reopened"] == 16
    assert contract["development_ordinal_16_rejected"] is True
    assert contract["development_accessible"] is False
    assert contract["legacy_train_interface_preserved"] is True
    assert receipt["publication"] == {
        "exact_candidate_ci": None,
        "exact_candidate_commit": None,
        "status": "pending",
    }
    assert receipt["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in receipt["protected_effects"].items()
        if key != "collection_authorized"
    )
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_successor_preflight_result_binds_exact_main_and_zero_effects() -> None:
    payload = PREFLIGHT_RESULT_PATH.read_bytes()
    receipt = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == PREFLIGHT_RESULT_SHA256
    assert receipt["status"] == (
        "one_rom_free_clustered_successor_train_preflight_passed_"
        "reorientation_complete_first_authentic_outcome_pending"
    )
    assert receipt["source"] == {
        "exact_ci_attempt": 1,
        "exact_ci_run": 33290594694,
        "exact_main_commit": "248346b049fde0ecd70f59277fc31ad9bce9a522",
        "source_bundle_sha256": (
            "53116a4a6c22950aefeebbea170274276759621719f68f875e0ae4457fd92435"
        ),
    }
    preflight = receipt["preflight"]
    assert preflight["ordinal"] == 0
    assert preflight["partition"] == "train"
    assert preflight["selected_root_reads"] == 1
    assert preflight["collection_authorized"] is False
    for field in (
        "behavior_commitments",
        "controller_actions",
        "counterfactual_targets",
        "development_outcomes_opened",
        "emulator_frames",
        "model_fits",
        "model_predictions",
        "private_identity_fields",
        "private_path_fields",
        "root_claims",
        "teacher_queries",
        "unselected_action_targets",
    ):
        assert preflight[field] == 0


def test_successor_preflight_result_records_bootstrap_miss_without_leakage() -> None:
    payload = PREFLIGHT_RESULT_PATH.read_text(encoding="ascii")
    receipt = json.loads(payload)
    miss = receipt["execution"]["bootstrap_miss"]

    assert receipt["execution"]["authenticated_preflight_invocations"] == 1
    assert receipt["execution"]["production_process_invocations_total"] == 2
    assert receipt["execution"]["retry_allowed"] is False
    assert miss["stage"] == "bootstrap_source_authentication"
    assert miss["authenticated_source_reached"] is False
    assert miss["private_root_opened"] is False
    assert miss["protected_effects_reachable"] is False
    assert receipt["learning_state"]["authentic_causal_train_examples"] == 6
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_successor_ordinal_zero_result_records_one_causal_example() -> None:
    payload = ORDINAL_ZERO_RESULT_PATH.read_bytes()
    receipt = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == ORDINAL_ZERO_RESULT_SHA256
    assert receipt["source"] == {
        "cartridge_sha256": (
            "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
        ),
        "exact_ci_attempt": 1,
        "exact_ci_run": 33292350018,
        "exact_main_commit": "00334dece0a080638df07660946871c4dab691c3",
        "source_bundle_sha256": (
            "53116a4a6c22950aefeebbea170274276759621719f68f875e0ae4457fd92435"
        ),
    }
    execution = receipt["execution"]
    assert execution["campaign_kind"] == "clustered_successor_train"
    assert execution["ordinal"] == 0
    assert execution["partition"] == "train"
    assert execution["causal_train_example_recorded"] is True
    assert execution["selected_candidate_target_only"] is True
    assert execution["behavior_commitments"] == 1
    assert execution["controller_actions"] == 5178
    assert execution["emulator_frames"] == 257093
    assert execution["provider_executions"] == 1
    assert execution["root_claims_metered_setup_only"] == 1
    assert execution["retry_allowed"] is False
    assert execution["automatic_retry_allowed"] is False


def test_successor_ordinal_zero_result_preserves_learning_and_privacy_boundaries() -> None:
    payload = ORDINAL_ZERO_RESULT_PATH.read_text(encoding="ascii")
    receipt = json.loads(payload)
    execution = receipt["execution"]
    learning = receipt["learning_state"]

    for field in (
        "counterfactual_targets",
        "development_outcomes_opened",
        "model_fits",
        "model_predictions",
        "private_identity_fields",
        "private_path_fields",
        "setup_behavior_draws_metered",
        "teacher_queries",
        "unselected_action_targets",
    ):
        assert execution[field] == 0
    assert learning["authentic_causal_train_examples_before"] == 6
    assert learning["authentic_causal_train_examples_after"] == 7
    assert learning["integration_fit_allowed_now"] is False
    assert learning["powered_model_fits"] == 0
    assert learning["authority_promotions"] == 0
    assert learning["transfer_results"] == 0
    assert receipt["privacy"]["selected_arm_identity_published"] is False
    assert receipt["privacy"]["selected_outcome_detail_published"] is False
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_successor_ordinal_one_result_reaches_only_the_example_count_floor() -> None:
    payload = ORDINAL_ONE_RESULT_PATH.read_bytes()
    receipt = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == ORDINAL_ONE_RESULT_SHA256
    assert receipt["source"] == {
        "cartridge_sha256": (
            "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
        ),
        "exact_ci_attempt": 1,
        "exact_ci_run": 33294371591,
        "exact_main_commit": "2ea86bcc6874952ce7281cb083062a099a91714b",
        "source_bundle_sha256": (
            "53116a4a6c22950aefeebbea170274276759621719f68f875e0ae4457fd92435"
        ),
    }
    execution = receipt["execution"]
    assert execution["campaign_kind"] == "clustered_successor_train"
    assert execution["ordinal"] == 1
    assert execution["partition"] == "train"
    assert execution["causal_train_example_recorded"] is True
    assert execution["selected_candidate_target_only"] is True
    assert execution["behavior_commitments"] == 1
    assert execution["controller_actions"] == 3322
    assert execution["emulator_frames"] == 146341
    assert execution["provider_executions"] == 1
    assert execution["root_claims_metered_setup_only"] == 1
    learning = receipt["learning_state"]
    assert learning["authentic_causal_train_examples_before"] == 7
    assert learning["authentic_causal_train_examples_after"] == 8
    assert learning["integration_example_count_gate_passed"] is True
    assert learning["integration_support_and_information_gate_pending"] is True
    assert learning["integration_fit_allowed_now"] is False


def test_successor_ordinal_one_result_preserves_fit_and_privacy_boundaries() -> None:
    payload = ORDINAL_ONE_RESULT_PATH.read_text(encoding="ascii")
    receipt = json.loads(payload)
    execution = receipt["execution"]
    learning = receipt["learning_state"]

    for field in (
        "counterfactual_targets",
        "development_outcomes_opened",
        "model_fits",
        "model_predictions",
        "private_identity_fields",
        "private_path_fields",
        "setup_behavior_draws_metered",
        "teacher_queries",
        "unselected_action_targets",
    ):
        assert execution[field] == 0
    assert execution["retry_allowed"] is False
    assert execution["automatic_retry_allowed"] is False
    assert learning["powered_model_fits"] == 0
    assert learning["authority_promotions"] == 0
    assert learning["transfer_results"] == 0
    assert receipt["privacy"]["selected_arm_identity_published"] is False
    assert receipt["privacy"]["selected_outcome_detail_published"] is False
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_integration_readiness_result_matches_the_one_complete_denominator_audit() -> None:
    machine_payload = INTEGRATION_READINESS_MACHINE_PATH.read_bytes()
    result_payload = INTEGRATION_READINESS_RESULT_PATH.read_bytes()
    machine = json.loads(machine_payload)
    result = json.loads(result_payload)

    assert (
        hashlib.sha256(machine_payload).hexdigest()
        == INTEGRATION_READINESS_MACHINE_SHA256
    )
    assert (
        hashlib.sha256(result_payload).hexdigest()
        == INTEGRATION_READINESS_RESULT_SHA256
    )
    assert result["source"]["machine_result_sha256"] == (
        INTEGRATION_READINESS_MACHINE_SHA256
    )
    assert result["source"]["exact_main_commit"] == (
        "ed6066e0bd6b6d6140aeb90935a76e26678b2b68"
    )
    assert result["source"]["exact_ci_run"] == 33298743000
    assert machine["complete_denominator_included"] is True
    assert machine["authentic_examples"] == 8
    assert machine["train_examples"] == 8
    assert machine["development_examples"] == 0
    assert machine["settled_examples"] == 8
    assert machine["censored_examples"] == 0
    assert machine["distinct_causal_identities"] == 8
    assert machine["distinct_decision_identities"] == 8
    assert machine["distinct_lineages"] == 8
    assert machine["maximum_lineage_multiplicity"] == 1
    assert machine["distinct_selected_option_kinds"] == 6
    assert machine["distinct_selected_feature_rows"] == 8
    assert machine["candidate_feature_rows"] == 24
    assert machine["supported_candidate_feature_rows"] == 24
    assert machine["variable_target_heads"] == 7
    assert machine["verified_success_varies"] is True
    assert machine["full_support_examples"] == 8
    assert machine["reason_codes"] == []
    assert machine["integration_fit_allowed"] is True


def test_integration_readiness_pass_grants_no_model_or_gameplay_authority() -> None:
    payload = INTEGRATION_READINESS_RESULT_PATH.read_text(encoding="ascii")
    result = json.loads(payload)
    execution = result["execution"]
    learning = result["learning_state"]

    assert execution["audit_invocations"] == 1
    assert execution["automatic_retry_allowed"] is False
    for field in (
        "controller_actions",
        "counterfactual_targets",
        "development_schedule_reads",
        "emulator_frames",
        "fit_executions",
        "model_predictions",
        "private_identity_fields",
        "private_path_fields",
        "root_claims",
        "teacher_queries",
        "unselected_action_targets",
    ):
        assert execution[field] == 0
    assert learning["authentic_causal_train_examples_before"] == 8
    assert learning["authentic_causal_train_examples_after"] == 8
    assert learning["integration_support_and_information_gate_passed"] is True
    assert learning["non_authoritative_integration_fit_allowed_now"] is True
    assert learning["integration_model_fits"] == 0
    assert learning["powered_model_fits"] == 0
    assert learning["authority_promotions"] == 0
    assert learning["transfer_results"] == 0
    assert "integration_model_fit_executed" in result["claim_boundary"]["unsupported"]
    assert "/Users/" not in payload
    assert "/Volumes/" not in payload


def test_integration_fit_result_matches_the_one_authentic_model_artifact() -> None:
    machine_payload = INTEGRATION_FIT_MACHINE_PATH.read_bytes()
    result_payload = INTEGRATION_FIT_RESULT_PATH.read_bytes()
    machine = json.loads(machine_payload)
    result = json.loads(result_payload)

    assert hashlib.sha256(machine_payload).hexdigest() == INTEGRATION_FIT_MACHINE_SHA256
    assert hashlib.sha256(result_payload).hexdigest() == INTEGRATION_FIT_RESULT_SHA256
    assert result["source"]["machine_result_sha256"] == INTEGRATION_FIT_MACHINE_SHA256
    assert result["source"]["exact_main_commit"] == (
        "f50979827a0faa62adf66c4ca828fd3cdb42a1c6"
    )
    assert result["source"]["exact_ci_run"] == 33320429925
    assert machine["fit_executions"] == 1
    assert machine["private_fit_claims"] == 1
    assert machine["complete_denominator_included"] is True
    assert machine["total_examples"] == 8
    assert machine["settled_examples"] == 8
    assert machine["censored_examples"] == 0
    assert machine["candidate_feature_rows"] == 24
    assert machine["supported_candidate_feature_rows"] == 24
    assert machine["variable_target_heads"] == 7
    assert machine["coefficient_finiteness"] == {
        "all_finite": True,
        "coefficients": 225,
        "finite_coefficients": 225,
    }
    assert machine["conditioning"]["number"] == 674.1219622149168
    assert machine["artifact"]["reload_bytes_equal"] is True
    assert machine["artifact"]["reload_model_equal"] is True


def test_integration_fit_result_preserves_rejected_launch_and_authority_boundary() -> None:
    failure_payload = INTEGRATION_FIT_FAILURE_MACHINE_PATH.read_bytes()
    result_payload = INTEGRATION_FIT_RESULT_PATH.read_text(encoding="ascii")
    failure = json.loads(failure_payload)
    result = json.loads(result_payload)

    assert (
        hashlib.sha256(failure_payload).hexdigest()
        == INTEGRATION_FIT_FAILURE_MACHINE_SHA256
    )
    assert failure["stage"] == "private_corpus_or_store"
    assert failure["fit_executions"] == 0
    assert failure["private_fit_claims"] == 0
    assert result["launch_history"]["pre_fit_rejected_invocations"] == 1
    assert result["launch_history"]["fit_invocations"] == 1
    assert result["learning_state"] == {
        "authentic_causal_train_examples_after": 8,
        "authentic_causal_train_examples_before": 8,
        "authority_promotions": 0,
        "integration_model_fits": 1,
        "powered_model_fits": 0,
        "transfer_results": 0,
    }
    for field in (
        "authority_promotions",
        "controller_actions",
        "counterfactual_targets",
        "crystal_accesses",
        "development_examples_read",
        "emulator_frames",
        "gameplay_model_predictions",
        "root_claims",
        "teacher_queries",
        "unselected_action_targets",
    ):
        assert result["effects"][field] == 0
    assert "model_quality_or_generalization" in result["claim_boundary"]["unsupported"]
    assert result["privacy"]["coefficient_values_published"] is False
    assert result["privacy"]["loss_values_published"] is False
    assert "/Users/" not in result_payload
    assert "/Volumes/" not in result_payload
