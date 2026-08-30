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
