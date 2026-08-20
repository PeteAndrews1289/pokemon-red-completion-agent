#!/usr/bin/env python3
"""Freeze a capable one-shot sealed evaluation plan from public metadata only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
    STRATEGIC_NAVIGATION_LINEAR_MODEL_ID,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_test_design import (
    STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES,
)

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "configs" / "red-strategic-navigation-sealed-evaluation-v1.json"
DIGEST_PATH = ROOT / "configs" / "red-strategic-navigation-sealed-evaluation-v1.digest.json"
DEVELOPMENT_RECEIPT = (
    ROOT / "docs" / "evidence" / "strategic-navigation-linear-development-2026-08-13.json"
)
STRATEGIC_COLLECTION_REGISTRY = ROOT / "configs" / "red-strategic-navigation-collection-v1.json"
PLAN_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-plan-v9"
DIGEST_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-plan-digest-v9"
CASE_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-case-v1"
EVALUATION_ID = "red-strategic-navigation-sealed-evaluation-v1"
V1_PLAN_SHA256 = "ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b"
V2_PLAN_SHA256 = "230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537"
V3_PLAN_SHA256 = "f4429dce83b99c4c5dce05785b2222e590c6d670adc0966d8f6b86e5c88d4fec"
V4_PLAN_SHA256 = "63b3855463fcf8834ee8ae7635df1726b78fcde52257b0c7c5a3ecb26de131d7"
V5_PLAN_SHA256 = "2f7ec30b096655d23626a7a98107df770fe7e9a26943240a45f5887e72a5cba6"
V6_PLAN_SHA256 = "9df65487806d80b7d37e074c6f1ecf0ddf615e9853f7615e5681975e461ff440"
V7_PLAN_SHA256 = "d5ade0bf749b24f5d266f568daa7da96b715b166bd05c41c473f6d91722f582a"
V8_PLAN_SHA256 = "fe208ac5cf628bcd7301ae500622ae59e39bea271f60d817e2f70f3001fcc5d9"
FROZEN_MODEL_SHA256 = "753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1"
FROZEN_MODEL_FILE_SHA256 = "6ef826bc92fae3092e9ccaefaad4107a687a564f7d35818f844fadba68540cdd"
FROZEN_FEATURES = (
    "candidate.route_cost.relative_rank",
    "candidate.route_steps.relative_rank",
    "candidate.map_transitions.relative_rank",
    "candidate.field_actions.relative_rank",
    "candidate.mode_changes.relative_rank",
)

# This lane is deliberately paused while the transferable goal manager is the
# active experiment.  Source changes outside the frozen evaluator invalidate
# its old authorization, but must not silently rewrite a one-shot plan.  A
# future explicit reauthorization can regenerate a successor plan.
PAUSE_FREEZE_EXISTING_PLAN = True
PAUSED_PLAN_BYTES = 13_979
PAUSED_PLAN_SHA256 = "40b7daff70127f8df53ad73db79eea97ad7408a6152647418a0105c4ea1a6138"


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


def _generated_payloads() -> tuple[bytes, bytes, dict[str, object]]:
    registry = load_strategic_navigation_scenario_registry(ROOT)
    teacher_execution = parse_strategic_navigation_registry(
        STRATEGIC_COLLECTION_REGISTRY.read_bytes()
    ).execution
    test_scenarios = tuple(
        scenario for scenario in registry.scenarios if scenario.partition == "test"
    )
    cases = []
    for ordinal, scenario in enumerate(test_scenarios, start=1):
        completed_regions = {
            COMPLETION_QUEST.objective(objective_id).target_region
            for objective_id in scenario.completed_objective_ids
        }
        local_non_teacher = tuple(
            objective_id
            for objective_id in scenario.candidate_objective_ids
            if objective_id != scenario.teacher_objective_id
            and COMPLETION_QUEST.objective(objective_id).target_region in completed_regions
        )
        challenge = bool(local_non_teacher)
        challenged_objective_id = local_non_teacher[0] if local_non_teacher else None
        origin_region = scenario.origin_region
        if challenged_objective_id is not None:
            target_region = COMPLETION_QUEST.objective(challenged_objective_id).target_region
            if target_region is None:
                raise RuntimeError("sealed challenge objective lacks a target region")
            origin_region = target_region
        case = {
            "case_id": f"red-strategic-sealed-v1-{ordinal:03d}-test",
            "challenged_non_teacher_objective_id": challenged_objective_id,
            "cost_baseline_challenge_hypothesis": challenge,
            "origin_region": origin_region,
            "schema": CASE_SCHEMA,
            "source_scenario_id": scenario.scenario_id,
            "source_scenario_sha256": scenario.scenario_sha256,
        }
        case["case_sha256"] = canonical_sha256(case)
        cases.append(case)
    challenge_count = sum(bool(case["cost_baseline_challenge_hypothesis"]) for case in cases)
    if len(cases) != 12 or challenge_count != 10:
        raise RuntimeError("sealed evaluation case capability differs")
    candidate_counts_by_case = {
        str(case["case_id"]): len(scenario.candidate_objective_ids)
        for case, scenario in zip(cases, test_scenarios, strict=True)
    }
    case_order = [str(case["case_id"]) for case in cases]

    source_bundle_sha256 = working_source_bundle_sha256(ROOT)
    if teacher_execution.source_bundle_sha256 != source_bundle_sha256:
        raise RuntimeError("sealed teacher execution source differs")
    document = {
        "access_policy": {
            "private_test_inputs_opened_at_freeze": 0,
            "requires_clean_published_exact_source": True,
            "requires_external_audit": (
                "typed_approved_for_authorization_receipt_bound_to_plan_source_bundle_and_commit"
            ),
            "requires_non_test_adapter_qualification": (
                "typed_passed_zero_test_access_receipt_bound_to_plan_source_bundle_and_commit"
            ),
            "requires_owner_authorization": True,
        },
        "adapter_policy": {
            "candidate_order": "source_bound_assignment_hash_v1",
            "candidate_planning": "after_authenticated_challenge_relocation",
            "case_catalog_schema": ("pokemon-strategic-navigation-sealed-case-catalog-v1"),
            "challenge_relocation": (
                "after_claim_deterministic_route_to_declared_origin_with_zero_objective_delta"
            ),
            "catalog_contains_private_paths": False,
            "catalog_contains_route_costs_or_answers": False,
            "input_representation": "unlabeled_identity_free_policy_question",
            "non_test_qualification_failure": (
                "typed_failed_receipt_zero_test_access_and_nonzero_exit"
            ),
            "private_case_open": "only_after_durable_case_claim",
            "teacher_execution": "only_after_durable_prediction_commitment",
        },
        "attempt_policy": {
            "attempts_per_case": 1,
            "failed_attempt_is_consumed": True,
            "omission_allowed": False,
            "publish_every_case": True,
            "rerun_allowed": False,
        },
        "amendments": [
            {
                "amended_before_private_access": True,
                "change": ("primary_endpoint_restricted_to_preregistered_challenge_cases"),
                "reason": (
                    "independent_power_audit_found_non_challenge_cases_"
                    "asymmetric_for_primary_pairing"
                ),
                "supersedes_plan_sha256": V1_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": "bind_fail_closed_executor_and_optional_stopping_contract",
                "reason": ("external_audit_required_durable_claim_before_private_case_access"),
                "supersedes_plan_sha256": V2_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": "bind_case_catalog_and_cartridge_adapter_contract",
                "reason": (
                    "complete_prediction_first_private_input_adapter_before_"
                    "external_audit_and_owner_authorization"
                ),
                "supersedes_plan_sha256": V3_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": "bind_authenticated_challenge_relocation_contract",
                "reason": (
                    "independent_adapter_audit_found_source_and_declared_challenge_origins_differ"
                ),
                "supersedes_plan_sha256": V4_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": "bind_readiness_receipts_and_unforgeable_runtime_objects",
                "reason": (
                    "self_audit_found_descriptive_gates_and_copyable_"
                    "validation_tokens_were_not_sufficient"
                ),
                "supersedes_plan_sha256": V5_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": (
                    "bind_typed_receipt_verdicts_and_shared_non_test_production_qualification"
                ),
                "reason": (
                    "external_audit_found_bare_receipt_digests_could_not_"
                    "distinguish_unfavorable_verdicts"
                ),
                "supersedes_plan_sha256": V6_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": (
                    "bind_directional_warp_arrival_and_durable_failed_qualification_receipts"
                ),
                "reason": (
                    "live_non_test_saffron_cinnabar_qualification_exposed_"
                    "directional_door_arrival_mismatch"
                ),
                "supersedes_plan_sha256": V7_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": ("bind_destination_warp_trigger_and_connection_arrival_semantics"),
                "reason": (
                    "published_hard_non_test_qualification_exposed_destination_"
                    "trigger_and_connection_arrival_semantics"
                ),
                "supersedes_plan_sha256": V8_PLAN_SHA256,
            },
        ],
        "baseline": {
            "policy_id": "unique-minimum-route-cost-v1",
            "prediction_tie": "incorrect",
        },
        "cases": cases,
        "endpoint_policy": {
            "all_case_accuracy": {
                "case_filter": "all_registered_cases",
                "expected_case_count": len(cases),
                "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
                "role": "mandatory_descriptive_report",
            },
            "candidate_count_accuracy": {
                "case_filter": "all_registered_cases",
                "group_by": "candidate_count",
                "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
                "role": "mandatory_descriptive_report",
            },
            "primary": {
                "case_filter": "cost_baseline_challenge_hypothesis_true",
                "expected_case_count": challenge_count,
                "minimum_measured_teacher_baseline_disagreements": 6,
                "paired_test": ("two_sided_exact_mcnemar_on_discordant_correctness"),
                "primary_unit": "one_unique_scenario",
                "required_direction": "model_paired_wins_exceed_losses",
                "required_successful_teacher_cases": challenge_count,
                "significance_threshold": 0.05,
            },
            "safety": {
                "case_filter": "cost_baseline_challenge_hypothesis_false",
                "criterion": ("all_cases_succeed_and_zero_model_incorrect_baseline_correct"),
                "expected_case_count": len(cases) - challenge_count,
                "failure_effect": ("block_live_authority_and_report_without_changing_primary_test"),
                "role": "preregistered_baseline_favorable_non_regression",
            },
        },
        "evaluation_id": EVALUATION_ID,
        "execution_policy": {
            "candidate_counts_by_case": candidate_counts_by_case,
            "case_claim": "durable_before_any_private_case_input_access",
            "case_order": case_order,
            "case_order_frozen": True,
            "halt_after_first_claim": "publish_protocol_failure",
            "intermediate_case_results": "forbidden",
            "intermediate_statistics": "forbidden",
            "prediction_commit": "durable_before_deterministic_teacher_action",
            "prepared_session_abort": (
                "close_without_teacher_action_on_commitment_or_orchestration_failure"
            ),
            "reopen_consumed_case": False,
            "restart_after_claim": (
                "consume_open_case_as_both_incorrect_continue_next_mark_protocol_failure"
            ),
            "score_after_consumed_cases": len(cases),
            "single_continuous_invocation_required": True,
        },
        "execution_source_bundle_sha256": source_bundle_sha256,
        "frozen_model": {
            "canonical_sha256": FROZEN_MODEL_SHA256,
            "enabled_feature_names": list(FROZEN_FEATURES),
            "feature_schema_id": STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
            "feature_set_id": "relative_route",
            "l2": 0.1,
            "model_id": STRATEGIC_NAVIGATION_LINEAR_MODEL_ID,
            "parameter_count": 5,
            "private_file_sha256": FROZEN_MODEL_FILE_SHA256,
            "training_epochs": 600,
        },
        "minimum_challenge_hypotheses": (STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES),
        "preregistered_challenge_hypotheses": challenge_count,
        "scoring_policy": {
            "candidate_unavailable_after_claim": ("case_consumed_model_and_baseline_incorrect"),
            "failed_or_interrupted_after_claim": ("case_consumed_model_and_baseline_incorrect"),
            "incomplete_episode": "case_consumed_model_and_baseline_incorrect",
            "missing_case": "publish_incomplete_evaluation_as_protocol_failure",
            "model_prediction_tie": "incorrect",
            "teacher_target": "successful_deterministic_teacher_choice_only",
            "preclaim_identity_or_catalog_failure": ("open_zero_cases_and_refuse_execution"),
        },
        "schema": PLAN_SCHEMA,
        "source_scenario_registry_sha256": registry.registry_sha256,
        "teacher_execution": {
            "behavior_configuration_sha256": (teacher_execution.behavior_configuration_sha256),
            "decision_contract_sha256": teacher_execution.decision_contract_sha256,
            "objective_graph_sha256": teacher_execution.objective_graph_sha256,
            "source_bundle_sha256": teacher_execution.source_bundle_sha256,
            "teacher_execution_sha256": teacher_execution.teacher_execution_sha256,
        },
        "training_development_receipt_sha256": hashlib.sha256(
            DEVELOPMENT_RECEIPT.read_bytes()
        ).hexdigest(),
    }
    payload = _canonical_line(document)
    digest = hashlib.sha256(payload).hexdigest()
    digest_payload = _canonical_line(
        {
            "bytes": len(payload),
            "schema": DIGEST_SCHEMA,
            "sha256": digest,
        }
    )
    summary = {
        "bytes": len(payload),
        "evaluation_id": EVALUATION_ID,
        "plan_sha256": digest,
        "primary_endpoint_cases": challenge_count,
        "case_order_sha256": canonical_sha256(case_order),
        "intermediate_metrics_allowed": False,
        "preregistered_challenge_hypotheses": challenge_count,
        "private_test_inputs_opened": 0,
        "safety_endpoint_cases": len(cases) - challenge_count,
        "test_cases": len(cases),
    }
    return payload, digest_payload, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        if PAUSE_FREEZE_EXISTING_PLAN:
            if not PLAN_PATH.is_file() or not DIGEST_PATH.is_file():
                raise SystemExit("paused strategic sealed evaluation plan is absent")
            payload = PLAN_PATH.read_bytes()
            try:
                digest = json.loads(DIGEST_PATH.read_bytes())
                document = json.loads(payload)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise SystemExit("paused strategic sealed evaluation plan is invalid") from error
            if (
                len(payload) != PAUSED_PLAN_BYTES
                or hashlib.sha256(payload).hexdigest() != PAUSED_PLAN_SHA256
                or not isinstance(document, dict)
                or document.get("schema") != PLAN_SCHEMA
                or not isinstance(digest, dict)
                or digest.get("schema") != DIGEST_SCHEMA
                or digest.get("bytes") != len(payload)
                or digest.get("sha256") != hashlib.sha256(payload).hexdigest()
            ):
                raise SystemExit("paused strategic sealed evaluation plan digest differs")
            print(
                json.dumps(
                    {
                        "bytes": len(payload),
                        "paused": True,
                        "plan_sha256": hashlib.sha256(payload).hexdigest(),
                        "private_test_inputs_opened": 0,
                    },
                    sort_keys=True,
                )
            )
            return
        payload, digest_payload, summary = _generated_payloads()
        if (
            not PLAN_PATH.is_file()
            or not DIGEST_PATH.is_file()
            or PLAN_PATH.read_bytes() != payload
            or DIGEST_PATH.read_bytes() != digest_payload
        ):
            raise SystemExit("strategic sealed evaluation plan is stale")
    else:
        if PAUSE_FREEZE_EXISTING_PLAN:
            raise SystemExit(
                "strategic sealed evaluation is paused; create an explicitly reviewed successor"
            )
        payload, digest_payload, summary = _generated_payloads()
        PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLAN_PATH.write_bytes(payload)
        DIGEST_PATH.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
